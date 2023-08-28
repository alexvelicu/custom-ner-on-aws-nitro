#!/bin/bash

# Uses AWS CloudFormation to deploy a Nitro enclave and other necessary ressources
#
# Copyright Smals Research, 2023.
# Author: Fabien A. P. Petitcolas

parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"

STACK_NAME=NER-API
REGION=eu-west-1
CLI_PROFILE=mailchain-sandbox
OWNER_CONTACT=fape
KEY_NAME=nitro-test

if [[ $1 = "--bastion" ]]; then
  DEPLOYMENT_SCRIPT=nitro-enclave-bastion.yaml
else
  DEPLOYMENT_SCRIPT=nitro-enclave.yaml
fi

# Deploy the CloudFormation template
echo -e "\n\n========== Deploying $DEPLOYMENT_SCRIPT script as $STACK_NAME stack =========="
aws cloudformation deploy --region $REGION \
    --profile $CLI_PROFILE \
    --stack-name $STACK_NAME \
    --template-file $DEPLOYMENT_SCRIPT \
    --no-fail-on-empty-changeset \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
    OwnerContact=$OWNER_CONTACT \
    KeyName=$KEY_NAME

# If the deployment succeeded, show the IP adresses of the instances
if [ $? -eq 0 ]; then
  aws cloudformation list-exports \
    --profile $CLI_PROFILE \
    --region $REGION \
    --query "Exports[? ends_with(Name,'Ip') && ExportingStackId.contains(@, '$STACK_NAME')].[Name, Value]"
fi