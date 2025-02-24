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
from __future__ import annotations

import os
import typing
from pathlib import Path
from typing import Any, Callable

import digitalhub as dh
from digitalhub.context.api import get_context
from digitalhub.runtimes.enums import RuntimeEnvVar
from digitalhub_runtime_python.utils.configuration import import_function_and_init_from_source
from digitalhub_runtime_python.utils.inputs import compose_init, compose_inputs
from digitalhub_runtime_python.utils.outputs import build_status, parse_outputs

if typing.TYPE_CHECKING:
    from digitalhub_runtime_python.entities.run.python_run.entity import RunPythonRun
    from nuclio_sdk import Context, Event, Response


DEFAULT_PY_FILE = "main.py"


def execute_user_init(init_function: Callable, context: Context, run: RunPythonRun) -> None:
    """
    Execute user init function.

    Parameters
    ----------
    init_function : Callable
        User init function.
    context : Context
        Nuclio context.
    run : RunPythonRun
        Run entity.

    Returns
    -------
    None
    """
    init_params: dict = run.spec.to_dict().get("init_parameters", {})
    params = compose_init(init_function, context, init_params)
    context.logger.info("Execute user init function.")
    init_function(**params)


def init_context(context: Context) -> None:
    """
    Set the context attributes.
    Collect project, run and functions.

    Parameters
    ----------
    context : Context
        Nuclio context.

    Returns
    -------
    None
    """
    context.logger.info("Initializing context...")

    # Get project
    project_name = os.getenv(RuntimeEnvVar.PROJECT.value)
    project = dh.get_project(project_name)

    # Set root directory from context
    ctx = get_context(project.name)
    ctx.root.mkdir(parents=True, exist_ok=True)

    # Get run
    run: RunPythonRun = dh.get_run(os.getenv(RuntimeEnvVar.RUN_ID.value), project=project_name)

    # Set running context
    context.logger.info("Starting execution.")
    run._start_execution()

    # Get inputs if they exist
    run.spec.inputs = run.inputs(as_dict=True)

    # Get function (and eventually init) to execute and
    # set it in the context. Path refers to the working
    # user dir (will be taken from run spec in the future),
    # default_py_file filename is "main.py", source is the
    # function source
    path = Path("/shared")
    source = run.spec.to_dict().get("source")
    func, init_function = import_function_and_init_from_source(path, source, DEFAULT_PY_FILE)

    # Set attributes
    setattr(context, "project", project)
    setattr(context, "run", run)
    setattr(context, "user_function", func)
    setattr(context, "root", ctx.root)

    # Execute user init function
    if init_function is not None:
        execute_user_init(init_function, context, run)

    context.logger.info("Context initialized.")


def handler_job(context: Context, event: Event) -> Response:
    """
    Nuclio handler for python function.

    Parameters
    ----------
    context : Context
        Nuclio context.
    event : Event
        Nuclio event.

    Returns
    -------
    Response
        Response.
    """
    ############################
    # Set inputs
    #############################
    try:
        spec: dict = context.run.spec.to_dict()
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
        raise e

    ############################
    # Execute function
    ############################
    try:
        project: str = context.project.name
        context.logger.info("Executing function.")
        if hasattr(context.user_function, "__wrapped__"):
            results = context.user_function(project, context.run.key, **func_args)
        else:
            exec_result = context.user_function(**func_args)
            results = parse_outputs(exec_result, list(spec.get("outputs", {})), project, context.run.key)
        context.logger.info(f"Output results: {results}")
    except Exception as e:
        raise e
    finally:
        context.run._finish_execution()

    ############################
    # Set run status
    ############################
    try:
        context.logger.info("Building run status.")
        status = build_status(results, spec.get("outputs", {}))
    except Exception as e:
        raise e
    finally:
        context.run._finish_execution()

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
        raise e
    finally:
        context.run._finish_execution()

    ############################
    # End
    ############################
    context.logger.info("Done.")
    return context.Response(body="OK", headers={}, content_type="text/plain", status_code=200)


def handler_serve(context: Context, event: Event) -> Any:
    """
    Main function.

    Parameters
    ----------
    context : Context
        Nuclio context.
    event : Event
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
        raise e
    finally:
        context.run._finish_execution()

    ############################
    # Call user function
    ############################
    try:
        context.logger.info("Calling user function.")
        return context.user_function(**func_args)
    except Exception as e:
        raise e
    finally:
        context.run._finish_execution()
