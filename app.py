#!/usr/bin/env python3
import os
import cdk_nag
import aws_cdk as cdk
from cdk_nag import NagSuppressions
from aws_cdk import Aspects
from insurance_policy_ai_assistant.insurance_policy_ai_assistant_stack import InsurancePolicyAiAssistantStack
from insurance_policy_ai_assistant.waf_stack import CloudFrontWafStack


app = cdk.App()

os.environ['model_id'] = 'global.anthropic.claude-haiku-4-5-20251001-v1:0'
os.environ['cloudfront_prefix_list'] = 'pl-3b927c52' #This is for "us-east-1 (N. Virginia)" region. You have to change this prefix list, if you are using a different AWS region. Refer: https://docs.aws.amazon.com/vpc/latest/userguide/working-with-aws-managed-prefix-lists.html

# Create WAF stack in us-east-1 (required for CloudFront)
waf_stack = CloudFrontWafStack(
    app, 
    "CloudFrontWafStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region='us-east-1'  # Must be us-east-1 for CloudFront WAF integration
    ),
    cross_region_references=True,
)

main_stack = InsurancePolicyAiAssistantStack(
    app, 
    "InsurancePolicyAiAssistantStack",
    web_acl_arn=waf_stack.web_acl.attr_arn,  # Pass WAF ARN directly
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"]),
        cross_region_references=True)

Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))

# Ensure WAF is created before main stack
main_stack.add_dependency(waf_stack)

NagSuppressions.add_stack_suppressions(main_stack, [{
    "id":"AwsSolutions-IAM4", 
    "reason":"CDK created resources. Kindly ignore"}])
NagSuppressions.add_stack_suppressions(main_stack, [{
    "id":"AwsSolutions-IAM5", 
    "reason":"CDK created resources. Kindly ignore"}])
NagSuppressions.add_stack_suppressions(main_stack, [{
    "id":"AwsSolutions-L1", 
    "reason":"CDK created resources. Kindly ignore"}])
    
app.synth()
