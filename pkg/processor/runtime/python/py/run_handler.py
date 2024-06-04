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
from importlib import reload
from pathlib import Path

import digitalhub as dh
import digitalhub_runtime_python
from digitalhub_runtime_python.utils.configuration import get_function_from_source
from digitalhub_runtime_python.utils.inputs import get_inputs_parameters
from digitalhub_runtime_python.utils.outputs import build_status, parse_outputs
import pip._internal as pip


def render_error(msg: str, context):
    """
    Render error messages.
    """
    context.logger.info(msg)
    return context.Response(body=msg,
                            headers={},
                            content_type='text/plain',
                            status_code=500)

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

    reload(dh)
    reload(digitalhub_runtime_python)


def handler(context, event) -> None:
    """
    Nuclio handler for python function.
    """

    ############################
    # Initialize
    #############################
    body = event.body
    if isinstance(body, bytes):
        body = json.loads(body)
    context.logger.info(f"Received event: {body}")

    context.logger.info("Starting task.")
    spec: dict = body["spec"]
    spec["inputs"] = context.run.spec.to_dict().get("inputs", {})
    project: str = body["project"]

    root_path = Path("digitalhub_runtime_python")
    root_path.mkdir(parents=True, exist_ok=True)


    ############################
    # Set inputs
    #############################
    try:
        context.logger.info("Collecting inputs.")
        fnc_args = get_inputs_parameters(
            spec.get("inputs", {}),
            spec.get("parameters", {}),
            root_path,
        )
    except Exception as e:
        msg = f"Something got wrong during input collection. {e.args}"
        return render_error(msg, context)


    ############################
    # Configure function
    ############################
    try:
        context.logger.info("Configuring execution.")
        fnc = get_function_from_source(root_path, spec.get("source", {}))
    except Exception as e:
        msg = f"Something got wrong during function configuration. {e.args}"
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
                                    list(spec.get("values", [])),
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
        status = build_status(
            results,
            spec.get("outputs", {}),
            spec.get("values", {}),
        )
    except Exception as e:
        msg = f"Something got wrong during building run status. {e.args}"
        return render_error(msg, context)


    ############################
    # Set status
    ############################
    try:
        context.logger.info(f"Setting new run status: {status}")
        context.run._set_status(status)
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

