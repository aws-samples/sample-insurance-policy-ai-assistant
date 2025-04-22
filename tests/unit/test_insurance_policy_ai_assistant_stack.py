import aws_cdk as core
import aws_cdk.assertions as assertions

from insurance_policy_ai_assistant.insurance_policy_ai_assistant_stack import InsurancePolicyAiAssistantStack

# example tests. To run these tests, uncomment this file along with the example
# resource in insurance_policy_ai_assistant/insurance_policy_ai_assistant_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = InsurancePolicyAiAssistantStack(app, "insurance-policy-ai-assistant")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
