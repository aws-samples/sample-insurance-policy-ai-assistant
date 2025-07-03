#!/usr/bin/env python3
import os
import cdk_nag
import aws_cdk as cdk
from cdk_nag import NagSuppressions
from aws_cdk import Aspects
from insurance_policy_ai_assistant.insurance_policy_ai_assistant_stack import InsurancePolicyAiAssistantStack

app = cdk.App()

os.environ['model_id'] = 'us.anthropic.claude-3-5-haiku-20241022-v1:0'
os.environ['cloudfront_prefix_list'] = 'pl-3b927c52' #This is for "us-east-1 (N. Virginia)" region. You have to change this prefix list, if you are using a different AWS region. Refer: https://docs.aws.amazon.com/vpc/latest/userguide/working-with-aws-managed-prefix-lists.html

stack = InsurancePolicyAiAssistantStack(app, "InsurancePolicyAiAssistantStack",
env=cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"]))

Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))

NagSuppressions.add_stack_suppressions(stack, [{
    "id":"AwsSolutions-IAM4", 
    "reason":"CDK created resources. Kindly ignore"}])
NagSuppressions.add_stack_suppressions(stack, [{
    "id":"AwsSolutions-IAM5", 
    "reason":"CDK created resources. Kindly ignore"}])
NagSuppressions.add_stack_suppressions(stack, [{
    "id":"AwsSolutions-L1", 
    "reason":"CDK created resources. Kindly ignore"}])
    
app.synth()
