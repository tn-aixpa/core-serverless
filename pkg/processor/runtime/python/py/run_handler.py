# Copyright 2023 The DH Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import os
from typing import Any

import digitalhub as dh
from digitalhub.context.api import get_context
from digitalhub.entities._commons.enums import EntityTypes
from digitalhub_runtime_python.utils.inputs import compose_inputs
from digitalhub_runtime_python.utils.nuclio_configuration import import_function_and_init
from digitalhub_runtime_python.utils.outputs import build_status, parse_outputs
from digitalhub_runtime_python.entities.run.python_run.builder import RunPythonRunBuilder


def render_error(msg: str, context) -> Any:
    """
    Render error messages.

    Parameters
    ----------
    msg : str
        Error message.
    context
        Nuclio context.

    Returns
    -------
    Any
        User function response.
    """
    context.logger.info(msg)
    return context.Response(body=msg, headers={}, content_type="text/plain", status_code=500)


def init_context(context) -> None:
    """
    Set the context attributes.
    Collect project, run and functions.

    Parameters
    ----------
    context
        Nuclio context.

    Returns
    -------
    None
    """
    context.logger.info("Initializing context...")

    # Get project
    project_name = os.getenv("PROJECT_NAME")
    project = dh.get_project(project_name)

    # Set root directory from context
    root = get_context(project.name).root
    root.mkdir(parents=True, exist_ok=True)

    # Get run
    run_id = os.getenv("RUN_ID")
    run_key = f"store://{project.name}/{EntityTypes.RUN.value}/{RunPythonRunBuilder().ENTITY_KIND}/{run_id}"
    run = dh.get_run(run_key)

    # Get inputs if they exist
    run.spec.inputs = run.inputs(as_dict=True)

    # Get function (and eventually init) to execute and
    # set it in the context
    func, init_function = import_function_and_init(run.spec.to_dict().get("source"))

    # Set attributes
    setattr(context, "project", project)
    setattr(context, "run", run)
    setattr(context, "user_function", func)
    setattr(context, "root", root)

    # Execute user init function
    if init_function is not None:
        context.logger.info("Execute user init function.")
        init_function(context)

    context.logger.info("Context initialized.")


def handler_job(context, event) -> Any:
    """
    Nuclio handler for python function.

    Parameters
    ----------
    context
        Nuclio context.
    event : Event
        Nuclio event.

    Returns
    -------
    Response
        Response.
    """
    ############################
    # Initialize
    #############################
    if isinstance(event.body, bytes):
        body: dict = json.loads(event.body)
    else:
        body: dict = event.body
    context.logger.info(f"Received event: {body}")

    context.logger.info("Starting task.")
    spec: dict = body["spec"]
    spec["inputs"] = context.run.spec.to_dict().get("inputs", {})
    project: str = body["project"]

    ############################
    # Set inputs
    #############################
    try:
        context.logger.info("Configuring function inputs.")
        func_args = compose_inputs(
            spec.get("inputs", {}),
            spec.get("parameters", {}),
            False,
            context.user_function,
            context.project,
            context,
            event,
        )
    except Exception as e:
        msg = f"Something got wrong during function inputs configuration. {e.args}"
        return render_error(msg, context)

    ############################
    # Execute function
    ############################
    try:
        context.logger.info("Executing run.")
        if hasattr(context.user_function, "__wrapped__"):
            results = context.user_function(project, context.run.key, **func_args)
        else:
            exec_result = context.user_function(**func_args)
            results = parse_outputs(exec_result, list(spec.get("outputs", {})), project, context.run.key)
        context.logger.info(f"Output results: {results}")
    except Exception as e:
        msg = f"Something got wrong during function execution. {e.args}"
        return render_error(msg, context)

    ############################
    # Set run status
    ############################
    try:
        context.logger.info("Building run status.")
        status = build_status(results, spec.get("outputs", {}))
    except Exception as e:
        msg = f"Something got wrong during building run status. {e.args}"
        return render_error(msg, context)

    ############################
    # Set status
    ############################
    try:
        context.logger.info(f"Setting new run status: {status}")
        context.run.refresh()
        new_status = {**status, **context.run.status.to_dict()}
        context.run._set_status(new_status)
        context.run.save(update=True)
    except Exception as e:
        msg = f"Something got wrong during run status setting. {e.args}"
        return render_error(msg, context)

    ############################
    # End
    ############################
    context.logger.info("Done.")
    return context.Response(body="OK", headers={}, content_type="text/plain", status_code=200)


def handler_serve(context, event):
    """
    Main function.

    Parameters
    ----------
    context :
        Nuclio context.
    event :
        Nuclio event

    Returns
    -------
    Any
        User function response.
    """
    ############################
    # Set inputs
    #############################
    try:
        context.logger.info("Configuring function inputs.")
        func_args = compose_inputs(
            {},
            {},
            False,
            context.user_function,
            context.project,
            context,
            event,
        )
    except Exception as e:
        msg = f"Something got wrong during function inputs configuration. {e.args}"
        return render_error(msg, context)
    try:
        context.logger.info("Calling user function.")
        return context.user_function(**func_args)
    except Exception as e:
        msg = f"Something got wrong during function execution. {e.args}"
        return render_error(msg, context)
