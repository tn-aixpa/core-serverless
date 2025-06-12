# SPDX-FileCopyrightText: © 2025 DSLab - Fondazione Bruno Kessler
#
# SPDX-License-Identifier: Apache-2.0


GO_VERSION := $(shell go version | cut -d " " -f 3)
GOPATH ?= $(shell go env GOPATH)
SHELL:=/bin/bash


SERVERLESS_DOCKER_REPO=ghcr.io/scc-digitalhub/digitalhub-serverless
SERVERLESS_CACHE_REPO=ghcr.io/scc-digitalhub/digitalhub-serverless

# get default os / arch from go env
SERVERLESS_DEFAULT_OS := $(shell go env GOOS)
ifeq ($(GOARCH), arm)
	SERVERLESS_DEFAULT_ARCH := armhf
else ifeq ($(GOARCH), arm64)
	SERVERLESS_DEFAULT_ARCH := arm64
else
	SERVERLESS_DEFAULT_ARCH := $(shell go env GOARCH || echo amd64)
endif

# upstream repo
NUCLIO_DOCKER_REPO ?= quay.io/nuclio
NUCLIO_DOCKER_IMAGE_TAG ?= 1.13.2-$(SERVERLESS_DEFAULT_ARCH)


SERVERLESS_OS := $(if $(SERVERLESS_OS),$(SERVERLESS_OS),$(SERVERLESS_DEFAULT_OS))
SERVERLESS_ARCH := $(if $(SERVERLESS_ARCH),$(SERVERLESS_ARCH),$(SERVERLESS_DEFAULT_ARCH))
SERVERLESS_LABEL := $(if $(SERVERLESS_LABEL),$(SERVERLESS_LABEL),latest)
SERVERLESS_CACHE_LABEL := $(if $(SERVERLESS_CACHE_LABEL),$(SERVERLESS_CACHE_LABEL),unstable)

SERVERLESS_VERSION_GIT_COMMIT = $(shell git rev-parse HEAD)

SERVERLESS_DOCKER_IMAGE_TAG=$(SERVERLESS_LABEL)-$(SERVERLESS_ARCH)

SERVERLESS_DOCKER_IMAGE_CACHE_TAG=$(SERVERLESS_CACHE_LABEL)-$(SERVERLESS_ARCH)-cache

# Link flags
GO_LINK_FLAGS ?= -s -w
GO_LINK_FLAGS_INJECT_VERSION := $(GO_LINK_FLAGS) \
	-X github.com/v3io/version-go.gitCommit=$(SERVERLESS_VERSION_GIT_COMMIT) \
	-X github.com/v3io/version-go.label=$(SERVERLESS_LABEL) \
	-X github.com/v3io/version-go.arch=$(SERVERLESS_ARCH)

#
#  Must be first target
#
.PHONY: all
all:
	$(error "Please pick a target (run 'make targets' to view targets)")

#
# Build helpers
#

# tools get built with the specified OS/arch and inject version
GO_BUILD_CMD = go build -ldflags="$(GO_LINK_FLAGS_INJECT_VERSION)"

#
# Rules
#

.PHONY: build
build: docker-images tools
	@echo Done.

DOCKER_IMAGES_RULES ?= \
	processor \
	handler-builder-python-onbuild

DOCKER_IMAGES_CACHE ?=


.PHONY: docker-images
docker-images: $(DOCKER_IMAGES_RULES)
	@echo Done.

.PHONY: pull-docker-images-cache
pull-docker-images-cache:
	@printf '%s\n' $(DOCKER_IMAGES_CACHE) | xargs -n 1 -P 5 docker pull

.PHONY: push-docker-images-cache
push-docker-images-cache:
	@printf '%s\n' $(DOCKER_IMAGES_CACHE) | xargs -n 1 -P 5 docker push

.PHONY: tools
tools: ensure-gopath nuctl
	@echo Done.

.PHONY: push-docker-images
push-docker-images: print-docker-images
	@echo "Pushing images concurrently"
	@echo $(IMAGES_TO_PUSH) | xargs -n 1 -P 5 docker push
	@echo Done.

.PHONY: save-docker-images
save-docker-images: print-docker-images
	@echo "Saving Serverless docker images"
	docker save $(IMAGES_TO_PUSH) | gzip --fast > digitalhub-serverless-docker-images-$(SERVERLESS_LABEL)-$(SERVERLESS_ARCH).tar.gz

.PHONY: load-docker-images
load-docker-images: print-docker-images
	@echo "Load Serverless docker images"
	docker load -i digitalhub-serverless-docker-images-$(SERVERLESS_LABEL)-$(SERVERLESS_ARCH).tar.gz

.PHONY: print-docker-images
pull-docker-images: print-docker-images
	@echo "Pull Serverless docker images"
	@echo $(IMAGES_TO_PUSH) | xargs -n 1 -P 5 docker pull

.PHONY: retag-docker-images
retag-docker-images: print-docker-images
	$(eval SERVERLESS_NEW_LABEL ?= retagged)
	$(eval SERVERLESS_NEW_LABEL = ${SERVERLESS_NEW_LABEL}-${SERVERLESS_ARCH})
	@echo "Retagging Serverless docker images with ${SERVERLESS_NEW_LABEL}"
	echo $(IMAGES_TO_PUSH) | xargs -P 5 -I{} sh -c 'image="{}"; docker tag $$image $$(echo $$image | cut -d : -f 1):$(SERVERLESS_NEW_LABEL)'
	@echo "Done"

.PHONY: print-docker-images
print-docker-images:
	@# env to determine whether to print only first image
	$(eval PRINT_FIRST_IMAGE ?= false)
	@for image in $(IMAGES_TO_PUSH); do \
		echo $$image ; \
		if [ "$(PRINT_FIRST_IMAGE)" = "true" ]; then \
			break ; \
		fi ; \
	done


.PHONY: print-docker-images-cache
print-docker-images-cache:
	@echo "Serverless Docker images cache:"
	@for image in $(DOCKER_IMAGES_CACHE); do \
		echo $$image; \
	done


.PHONY: print-docker-image-rules-json
print-docker-image-rules-json:
	@/bin/echo -n "["
	@for image in $(DOCKER_IMAGES_RULES); do \
		/bin/echo -n "{\"image_rule\": \"$$image\"}" ; \
		if [ "$$image" != "$(lastword $(DOCKER_IMAGES_RULES))" ]; then \
			/bin/echo -n "," ; \
		fi ; \
	done
	@/bin/echo -n "]"

#
# Tools
#


SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME=$(SERVERLESS_DOCKER_REPO)/processor:$(SERVERLESS_DOCKER_IMAGE_TAG)
SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME_CACHE=$(SERVERLESS_CACHE_REPO)/processor:$(SERVERLESS_DOCKER_IMAGE_CACHE_TAG)

.PHONY: processor
processor: modules

	@# build processor locally
	@# build its image and copy from host to image
	@# this is done to avoid trying compiling the processor binary on the image
	@# while using virtualization / emulation to match the desired architecture
	@mkdir -p ./.bin
	GOARCH=$(SERVERLESS_ARCH) GOOS=linux CGO_ENABLED=0 $(GO_BUILD_CMD) \
        -o ./.bin/processor-$(SERVERLESS_ARCH) \
        cmd/processor/main.go

	docker build \
		--build-arg SERVERLESS_ARCH=$(SERVERLESS_ARCH) \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		--cache-from $(SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME_CACHE) \
		--file cmd/processor/Dockerfile \
		--tag $(SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME) \
		--tag $(SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME_CACHE) \
		.

ifneq ($(filter processor,$(DOCKER_IMAGES_RULES)),)
$(eval IMAGES_TO_PUSH += $(SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME))
$(eval DOCKER_IMAGES_CACHE += $(SERVERLESS_DOCKER_PROCESSOR_IMAGE_NAME_CACHE))
endif

#
# Onbuild images
#

# Python
SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME=\
 $(SERVERLESS_DOCKER_REPO)/handler-builder-python-onbuild:$(SERVERLESS_DOCKER_IMAGE_TAG)
SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME_CACHE=\
 $(SERVERLESS_CACHE_REPO)/handler-builder-python-onbuild:$(SERVERLESS_DOCKER_IMAGE_CACHE_TAG)

PIP_REQUIRE_VIRTUALENV=false

.PHONY: handler-builder-python-onbuild
handler-builder-python-onbuild: processor
	docker build \
		--build-arg NUCLIO_DOCKER_IMAGE_TAG=$(NUCLIO_DOCKER_IMAGE_TAG) \
		--build-arg NUCLIO_DOCKER_REPO=$(NUCLIO_DOCKER_REPO) \
		--build-arg SERVERLESS_DOCKER_IMAGE_TAG=$(SERVERLESS_DOCKER_IMAGE_TAG) \
		--build-arg SERVERLESS_DOCKER_REPO=$(SERVERLESS_DOCKER_REPO) \
		--cache-from $(SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME_CACHE) \
		--file pkg/processor/build/runtime/python/docker/onbuild/Dockerfile \
		--tag $(SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME) \
		--tag $(SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME_CACHE) \
		.

ifneq ($(filter handler-builder-python-onbuild,$(DOCKER_IMAGES_RULES)),)
$(eval IMAGES_TO_PUSH += $(SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME))
$(eval DOCKER_IMAGES_CACHE += $(SERVERLESS_DOCKER_HANDLER_BUILDER_PYTHON_ONBUILD_IMAGE_NAME_CACHE))
endif

#
# Misc
#

.PHONY: fmt
fmt:
	gofmt -s -w .
	golangci-lint run --fix

.PHONY: lint
lint: modules ensure-test-files-annotated
	@echo Installing linters...
	@test -e $(GOPATH)/bin/golangci-lint || \
	  	(curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $(GOPATH)/bin v1.54.2)

	@echo Linting...
	$(GOPATH)/bin/golangci-lint run -v
	@echo Done.

#
# Go env
#

.PHONY: ensure-gopath
ensure-gopath:
ifndef GOPATH
	$(error GOPATH must be set)
endif

.PHONY: modules
modules: ensure-gopath
	@go mod download

.PHONY: targets
targets:
	@awk -F: '/^[^ \t="]+:/ && !/PHONY/ {print $$1}' Makefile | sort -u
