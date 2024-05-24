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
import sys
import json

import digitalhub as dh
from digitalhub_core.entities._base.status import State

def handler(context, event) -> None:
    """
    Handler for python function.
    """
    body = event.body
    if isinstance(body, bytes):
        body = json.loads(body)

    project_name = body["project"]
    run_id = body["id"]

    context.logger.info(f"Running: {project_name} / {run_id}.")

    # Get project and run
    project = dh.get_project(project_name)
    run = dh.get_run(project.name, run_id)

    context.logger.info("Installing run dependencies.")
    for requirement in run.spec.to_dict().get("requirements", []):
        context.logger.info(f"Installing {requirement}.")
        os.system(f"pip install {requirement}")

    context.logger.info("Executing function.")
    run.run()

    if run.status.state == State.ERROR.value:
        return context.Response(body=json.dumps(run.status),
                            headers={},
                            content_type='text/plain',
                            status_code=500)
    
    context.logger.info("Done.")
    return context.Response(body=json.dumps(run.status),
                            headers={},
                            content_type='text/plain',
                            status_code=200)