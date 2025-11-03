from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_wafv2 as wafv2,
    CfnOutput
)
from constructs import Construct
import datetime

class CloudFrontWafStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        entryTimestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
        
        # Create WAF WebACL for CloudFront (must be in us-east-1)
        self.web_acl = wafv2.CfnWebACL(self, "CloudFrontWebACL",
            name=f"InsurancePolicyAIAssistant_ACL-{entryTimestamp}",
            scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow={}
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name=f"InsurancePolicyAIAssistant_ACL-{entryTimestamp}"
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="AWS-RateBasedRule-IP-300",
                    priority=0,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=100,
                            aggregate_key_type="IP"
                        )
                    ),
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        block={}
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"AWS-RateBasedRule-IP-300-{entryTimestamp}"
                    )
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="AWS-AWSManagedRulesAmazonIpReputationList",
                    priority=1,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesAmazonIpReputationList"
                        )
                    ),
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        none={}
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"AWS-AWSManagedRulesAmazonIpReputationList-{entryTimestamp}"
                    )
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="AWS-AWSManagedRulesCommonRuleSet",
                    priority=2,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        none={}
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"AWS-AWSManagedRulesCommonRuleSet-{entryTimestamp}"
                    )
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="AWS-AWSManagedRulesKnownBadInputsRuleSet",
                    priority=3,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesKnownBadInputsRuleSet"
                        )
                    ),
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        none={}
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        sampled_requests_enabled=True,
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"AWS-AWSManagedRulesKnownBadInputsRuleSet-{entryTimestamp}"
                    )
                )
            ]
        )
        
        self.web_acl.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Export the WebACL ARN for use in other stacks
        CfnOutput(
            self, "WebACLArn",
            value=self.web_acl.attr_arn,
            export_name="CloudFrontWebACLArn",
            description="CloudFront WebACL ARN"
        )
