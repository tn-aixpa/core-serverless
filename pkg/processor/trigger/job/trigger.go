/*
SPDX-FileCopyrightText: © 2025 DSLab - Fondazione Bruno Kessler

SPDX-License-Identifier: Apache-2.0
*/

package job

import (
	"time"

	"github.com/nuclio/errors"
	"github.com/nuclio/logger"
	"github.com/nuclio/nuclio-sdk-go"
	"github.com/nuclio/nuclio/pkg/common"
	"github.com/nuclio/nuclio/pkg/functionconfig"
	"github.com/nuclio/nuclio/pkg/processor/controlcommunication"
	"github.com/nuclio/nuclio/pkg/processor/trigger"
	"github.com/nuclio/nuclio/pkg/processor/worker"
)

type job struct {
	trigger.AbstractTrigger
	configuration *Configuration
}

func newTrigger(logger logger.Logger,
	workerAllocator worker.Allocator,
	configuration *Configuration,
	restartTriggerChan chan trigger.Trigger) (trigger.Trigger, error) {

	abstractTrigger, err := trigger.NewAbstractTrigger(logger,
		workerAllocator,
		&configuration.Configuration,
		"async",
		"job",
		configuration.Name,
		restartTriggerChan)
	if err != nil {
		return nil, errors.New("Failed to create abstract trigger")
	}

	newTrigger := job{
		AbstractTrigger: abstractTrigger,
		configuration:   configuration,
	}
	newTrigger.AbstractTrigger.Trigger = &newTrigger

	return &newTrigger, nil
}

func (k *job) Start(checkpoint functionconfig.Checkpoint) error {
	k.Logger.DebugWith("Starting job")

	go k.handleEvent()

	return nil
}

func (k *job) handleEvent() {
	response, submitError, processError := k.AllocateWorkerAndSubmitEvent( // nolint: errcheck
		&k.configuration.Event,
		k.Logger,
		10*time.Second)
	hasErr := submitError != nil || processError != nil

	switch typedResponse := response.(type) {
	case nuclio.Response:
		hasErr = hasErr || typedResponse.StatusCode != 200
	default:
	}

	controlMessage := &controlcommunication.ControlMessage{
		Kind: controlcommunication.ControlMessageKind("complete"),
		Attributes: map[string]interface{}{
			"status": hasErr,
		},
	}

	k.configuration.RuntimeConfiguration.ControlMessageBroker.SendToConsumers(controlMessage)
}

func (k *job) Stop(force bool) (functionconfig.Checkpoint, error) {
	return nil, nil
}

func (k *job) GetConfig() map[string]interface{} {
	return common.StructureToMap(k.configuration)
}
