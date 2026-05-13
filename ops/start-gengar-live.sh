#!/bin/bash
cd /Users/brain/hedge
export POLYMARKET_PRIVATE_KEY=0xdbab414025de26c1534b5d89bd2c836dd3ed26996f7a7ea6402dfbd423316f6a
npx tsx src/prediction/gengarExecutionWatcher.ts >> .rumbling-hedge/logs/gengar-execution.log 2>&1
