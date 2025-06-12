/*
SPDX-FileCopyrightText: © 2025 DSLab - Fondazione Bruno Kessler

SPDX-License-Identifier: Apache-2.0
*/

package job

import (
	"github.com/nuclio/nuclio/pkg/functionconfig"
	"github.com/nuclio/nuclio/pkg/processor/runtime"
	"github.com/nuclio/nuclio/pkg/processor/trigger"
	"github.com/nuclio/nuclio/pkg/processor/worker"

	"github.com/nuclio/errors"
	"github.com/nuclio/logger"
)

type factory struct {
	trigger.Factory
}

func (f *factory) Create(parentLogger logger.Logger,
	id string,
	triggerConfiguration *functionconfig.Trigger,
	runtimeConfiguration *runtime.Configuration,
	namedWorkerAllocators *worker.AllocatorSyncMap,
	restartTriggerChan chan trigger.Trigger) (trigger.Trigger, error) {

	// create logger parent
	triggerLogger := parentLogger.GetChild(triggerConfiguration.Kind)

	configuration, err := NewConfiguration(id, triggerConfiguration, runtimeConfiguration)
	if err != nil {
		return nil, errors.Wrap(err, "Failed to parse trigger configuration")
	}

	// get or create worker allocator
	workerAllocator, err := f.GetWorkerAllocator(triggerConfiguration.WorkerAllocatorName,
		namedWorkerAllocators,
		func() (worker.Allocator, error) {
			return worker.WorkerFactorySingleton.CreateFixedPoolWorkerAllocator(triggerLogger,
				configuration.NumWorkers,
				runtimeConfiguration)
		})

	if err != nil {
		return nil, errors.Wrap(err, "Failed to create worker allocator")
	}

	// finally, create the trigger (only 8080 for now)
	triggerInstance, err := newTrigger(triggerLogger,
		workerAllocator,
		configuration,
		restartTriggerChan)

	if err != nil {
		return nil, errors.Wrap(err, "Failed to create trigger")
	}

	return triggerInstance, nil
}

// register factory
func init() {
	trigger.RegistrySingleton.Register("job", &factory{})
}
