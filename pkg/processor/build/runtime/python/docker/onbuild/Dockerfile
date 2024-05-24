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

ARG SERVERLESS_DOCKER_IMAGE_TAG
ARG SERVERLESS_DOCKER_REPO=ghcr.io/scc-digitalhub/digitalhub-serverless
ARG NUCLIO_DOCKER_IMAGE_TAG
ARG NUCLIO_DOCKER_REPO=quay.io/nuclio

# # Supplies python 3.7 & common wheels
# FROM gcr.io/iguazio/python:3.7 as python37-builder
# COPY pkg/processor/runtime/python/py/requirements /requirements
# RUN pip download --dest /whl --exists-action i  --requirement /requirements/common.txt

# # Supplies python 3.8 & common wheels
# FROM gcr.io/iguazio/python:3.8 as python38-builder
# COPY pkg/processor/runtime/python/py/requirements /requirements
# RUN pip download --dest /whl --exists-action i  --requirement /requirements/common.txt

# Supplies python 3.9 & common wheels
FROM gcr.io/iguazio/python:3.9 as python39-builder
COPY pkg/processor/runtime/python/py/requirements /requirements
RUN pip download --dest /whl --exists-action i  --requirement /requirements/common.txt

# # Supplies python 3.10 & common wheels
# FROM gcr.io/iguazio/python:3.10 as python310-builder
# COPY pkg/processor/runtime/python/py/requirements /requirements
# RUN pip download --dest /whl --exists-action i  --requirement /requirements/common.txt

# # Supplies python 3.11 & common wheels
# FROM gcr.io/iguazio/python:3.11 as python311-builder
# COPY pkg/processor/runtime/python/py/requirements /requirements
# RUN pip download --dest /whl --exists-action i  --requirement /requirements/common.txt

# Supplies processor
FROM ${SERVERLESS_DOCKER_REPO}/processor:${SERVERLESS_DOCKER_IMAGE_TAG} as processor

FROM ${NUCLIO_DOCKER_REPO}/handler-builder-python-onbuild:${NUCLIO_DOCKER_IMAGE_TAG}

COPY pkg/processor/runtime/python/py /opt/nuclio

# Copy processor
COPY --from=processor /home/nuclio/bin/processor /home/nuclio/bin/processor
# Copy wheels
# COPY --from=python37-builder /whl /home/nuclio/bin/py3.7-whl
# COPY --from=python38-builder /whl /home/nuclio/bin/py3.8-whl
COPY --from=python39-builder /whl /home/nuclio/bin/py3.9-whl
# COPY --from=python310-builder /whl /home/nuclio/bin/py3.10-whl
# COPY --from=python311-builder /whl /home/nuclio/bin/py3.11-whl
