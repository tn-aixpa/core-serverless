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
import os
import json

import digitalhub as dh
from digitalhub_core.context.builder import get_context
from digitalhub_runtime_python.utils.configuration import get_function_from_source
from digitalhub_runtime_python.utils.inputs import compose_inputs
from digitalhub_runtime_python.utils.outputs import build_status, parse_outputs
import pip._internal as pip

from pathlib import Path
from typing import Callable
from digitalhub_core.utils.logger import LOGGER
from digitalhub_runtime_python.utils.configuration import save_function_source, parse_handler, import_function


def render_error(msg: str, context):
    """
    Render error messages.
    """
    context.logger.info(msg)
    return context.Response(body=msg,
                            headers={},
                            content_type='text/plain',
                            status_code=500)


def get_init_function(path: Path, source_spec: dict) -> Callable:
    """
    Get function from source.

    Parameters
    ----------
    path : Path
        Path where to save the function source.
    source_spec : dict
        Funcrion source spec.

    Returns
    -------
    Callable
        Function.
    """
    if "init_function" not in source_spec:
        return
    function_code = save_function_source(path, source_spec)
    handler_path, _ = parse_handler(source_spec["handler"])
    function_path = (function_code / handler_path).with_suffix(".py")
    return import_function(function_path, source_spec["init_function"])

def init_context(context) -> None:
    """
    Set the context attributes.
    """

    context.logger.info("Initializing context...")

    context.logger.info("Getting project and run.")
    project_name = os.getenv("PROJECT_NAME")
    run_id = os.getenv("RUN_ID")
    project = dh.get_project(project_name)
    run = dh.get_run(project_name, run_id)
    run.spec.inputs = run.inputs(as_dict=True)

    context.logger.info("Setting attributes.")
    setattr(context, "project", project)
    setattr(context, "run", run)

    context.logger.info("Installing requirements.")
    for req in run.spec.to_dict().get("requirements", []):
        context.logger.info(f"Adding requirement: {req}")
        pip.main(["install", req])

    root = get_context(project.name).root
    root.mkdir(parents=True, exist_ok=True)

    setattr(context, "root", root)

    try:
        init_function = get_init_function(root, run.spec.to_dict().get("source", {}))
        if init_function is not None:
            init_function(context)
    except Exception as e:
        msg = f"Something got wrong during init function configuration. {e.args}"
        return render_error(msg, context)

def handler_job(context, event) -> None:
    """
    Nuclio handler for python function.
    """

    ############################
    # Initialize
    #############################
    if isinstance(event.body, bytes):
        body = json.loads(event.body)
    context.logger.info(f"Received event: {body}")

    context.logger.info("Starting task.")
    spec: dict = body["spec"]
    spec["inputs"] = context.run.spec.to_dict().get("inputs", {})
    project: str = body["project"]

    ############################
    # Configure function
    ############################
    try:
        context.logger.info("Configuring execution.")
        fnc = get_function_from_source(context.root, spec.get("source", {}))
    except Exception as e:
        msg = f"Something got wrong during function configuration. {e.args}"
        return render_error(msg, context)


    ############################
    # Set inputs
    #############################
    try:
        context.logger.info("Configuring function inputs.")
        fnc_args = compose_inputs(
            spec.get("inputs", {}),
            spec.get("parameters", {}),
            False,
            fnc,
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
        if hasattr(fnc, '__wrapped__'):
            results = fnc(project, **fnc_args)
        else:
            exec_result = fnc(**fnc_args)
            results = parse_outputs(exec_result,
                                    list(spec.get("outputs", {})),
                                    project)
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
    return context.Response(body="OK",
                            headers={},
                            content_type='text/plain',
                            status_code=200)


def handler_serve(context, event) -> None:
    """
    Main function.
    """
    ############################
    # Initialize
    #############################
    context.logger.info("Starting task.")
    try:
        context.logger.info("Configuring execution.")
        fnc = get_function_from_source(context.root, context.run.spec.to_dict().get("source", {}))
    except Exception as e:
        msg = f"Something got wrong during function configuration. {e.args}"
        return render_error(msg, context)

    ############################
    # Execute function
    ############################
    try:
        context.logger.info("Executing run.")
        return fnc(context, event)
    except Exception as e:
        msg = f"Something got wrong during function execution. {e.args}"
        return render_error(msg, context)
