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
from pathlib import Path

from digitalhub_runtime_python.utils.configuration import get_function_from_source
from digitalhub_runtime_python.utils.inputs import get_inputs_parameters
from digitalhub_runtime_python.utils.outputs import build_status

import digitalhub as dh


def handler(context, event) -> None:
    """
    Nuclio handler for python function.
    """

    body = event.body
    if isinstance(body, bytes):
        body = json.loads(body)

    setattr(context, "project", dh.get_project(body["project"]))
    setattr(context, "run", dh.get_run(project, body["id"]))

    context.logger.info("Starting task.")
    spec: dict = body["spec"]
    project: str = body["project"]

    # Set root path
    root_path = Path("digitalhub_runtime_python")
    root_path.mkdir(parents=True, exist_ok=True)

    # Set inputs
    context.logger.info("Collecting inputs.")
    try:
        fnc_args = get_inputs_parameters(
            spec.get("inputs", {}),
            spec.get("parameters", {}),
            root_path,
        )
    except Exception:
        msg = "Something got wrong during input collection."
        context.logger.info(msg)
        return context.Response(body=msg,
                                headers={},
                                content_type='text/plain',
                                status_code=500)

    # Configure function by source
    context.logger.info("Configuring execution.")
    try:
        fnc = get_function_from_source(root_path, spec.get("source", {}))
    except Exception:
        msg = "Something got wrong during function configuration."
        context.logger.info(msg)
        return context.Response(body=msg,
                                headers={},
                                content_type='text/plain',
                                status_code=500)

    # Execute function
    context.logger.info("Executing run.")
    try:
        results = fnc(project, **fnc_args)
    except Exception:
        msg = "Something got wrong during function execution."
        context.logger.info(msg)
        return context.Response(body=msg,
                                headers={},
                                content_type='text/plain',
                                status_code=500)

    # Set run status
    context.logger.info("Setting run status.")
    status = build_status(
        results,
        spec.get("outputs", {}),
        spec.get("values", {}),
    )
    context.run._set_status(status)
    context.run.save(update=True)

    # Done
    context.context.logger.info("Done.")
    return context.Response(body=json.dumps(status),
                            headers={},
                            content_type='text/plain',
                            status_code=200)

