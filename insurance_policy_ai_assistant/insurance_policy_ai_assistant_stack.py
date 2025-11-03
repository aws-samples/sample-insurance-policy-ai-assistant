import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_iam as iam,
    aws_s3 as s3,
    aws_ec2 as ec2,
    custom_resources as cr,
    CustomResource,
    aws_s3_deployment as s3deploy,
    aws_dynamodb as dynamodb,
    aws_cognito as cognito,
    aws_lambda as _lambda,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_bedrock,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as elasticloadbalancingv2_targets
)
from aws_cdk.aws_lambda import Runtime, Code
from constructs import Construct
from cdk_nag import NagSuppressions
import datetime
from cdklabs.generative_ai_cdk_constructs import (
    bedrock 
    )


class InsurancePolicyAiAssistantStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, web_acl_arn: str = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        entryTimestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
        cloudfront_prefix = os.environ.get('cloudfront_prefix_list')
        # The code that defines your stack goes here
        
        #Creates Bedrock KB using the generative_ai_cdk_constructs. More info: https://github.com/awslabs/generative-ai-cdk-constructs
        #If you would like to switch the embedding model: https://awslabs.github.io/generative-ai-cdk-constructs/apidocs/namespaces/bedrock/classes/BedrockFoundationModel.html
        kb = bedrock.VectorKnowledgeBase(self, 'KnowledgeBase', 
                    embeddings_model= bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024, 
                    instruction=  'Use this knowledge base to answer questions about motor insurance policy.',
                    description= 'This knowledge base contains General Insurance Policy Documents.',
                )
        
        KB_ID = kb.knowledge_base_id
        
        #Creating Amazon Bedrock Guardrails
        guardrail = aws_bedrock.CfnGuardrail(self, "InsurancePolicyAIAssistant",
            name="insurance-policy-ai-assistant",
            blocked_input_messaging="Your input contains restricted content. Please rephrase your request.",
            blocked_outputs_messaging="The response contains restricted content and cannot be provided.",
            
            # Content policy for harmful content filtering
            content_policy_config=aws_bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    aws_bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    aws_bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="SEXUAL",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    aws_bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="VIOLENCE",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    aws_bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="INSULTS",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    aws_bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="MISCONDUCT",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    aws_bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="PROMPT_ATTACK",
                        input_strength="HIGH",
                        output_strength="NONE"
                    )
                ]
            ),
            
            # Word policy for profanity filtering
            word_policy_config=aws_bedrock.CfnGuardrail.WordPolicyConfigProperty(
                managed_word_lists_config=[
                    aws_bedrock.CfnGuardrail.ManagedWordsConfigProperty(
                        type="PROFANITY"
                    )
                ]
            ),
            
            # Contextual grounding for relevance and grounding checks
            contextual_grounding_policy_config=aws_bedrock.CfnGuardrail.ContextualGroundingPolicyConfigProperty(
                filters_config=[
                    aws_bedrock.CfnGuardrail.ContextualGroundingFilterConfigProperty(
                        type="RELEVANCE",
                        threshold=0.5
                    ),
                    aws_bedrock.CfnGuardrail.ContextualGroundingFilterConfigProperty(
                        type="GROUNDING",
                        threshold=0.5
                    )
                ]
            )
        )
        BEDROCK_GUARDRAIL_ID = guardrail.attr_guardrail_id

        # Create a bucket for server access logs
        accessLogsBucket = s3.Bucket(self, 'insurance-policy-ai-assistant-server-access-logs',
        enforce_ssl=True,
        removal_policy=RemovalPolicy.DESTROY,
        auto_delete_objects=True,
        access_control=s3.BucketAccessControl.LOG_DELIVERY_WRITE
        )
        
        accessLogsBucket_arn = accessLogsBucket.bucket_arn

        #Create S3 bucket where general insurance documents are stored
        #Name of the S3 bucket will be name of stack followed by insurance-policy-kb
        docBucket = s3.Bucket(self, 'insurance-policy-kb',
        removal_policy=RemovalPolicy.DESTROY,
        enforce_ssl=True,
        auto_delete_objects=True)
        
        docBucket_arn = docBucket.bucket_arn
        
        #S3 Bucket where customer policy is stored
        policyBucket = s3.Bucket(self, 'customer-policy',
        removal_policy=RemovalPolicy.DESTROY,
        enforce_ssl=True,
        auto_delete_objects=True)
        
        BUCKET_NAME = policyBucket.bucket_name
        policyBucket_arn = policyBucket.bucket_arn
        
        #Uploading general insurance documents to the corresponding S3 bucket [docBucket]
        deploy = s3deploy.BucketDeployment(self, "uploadpolicydocs",
            sources=[s3deploy.Source.asset('./policy_docs')],
            destination_bucket=docBucket
            )
        
        #Uploading customer policy document to the corresponding S3 bucket [policyBucket]
        policy_deploy = s3deploy.BucketDeployment(self, "uploadcustomerpolicy",
            sources=[s3deploy.Source.asset('./customer_policy')],
            destination_bucket=policyBucket
            )
            
        NagSuppressions.add_resource_suppressions([docBucket,policyBucket, accessLogsBucket], [
            {
                "id": "AwsSolutions-S1",
                "reason": "Bucket access logs are not required for this demo."
            }
        ])
        
        
        #Adds the created S3 bucket [docBucket] as a Data Source for Bedrock KB
        dataSource = bedrock.S3DataSource(self, 'DataSource',
            bucket= docBucket,
            knowledge_base=kb,
            data_source_name='insurance-policy-docs',
            chunking_strategy= bedrock.ChunkingStrategy.FIXED_SIZE,
        )
        
        
        # Data Ingestion Params
        
        dataSourceIngestionParams = {
            "dataSourceId": dataSource.data_source_id,
            "knowledgeBaseId": KB_ID,
        }
        
         # Define a custom resource to make an AwsSdk startIngestionJob call. This will do an initial sync of the S3 bucket [docBucket].    
        ingestion_job_cr = cr.AwsCustomResource(self, "IngestionCustomResource",
            on_create=cr.AwsSdkCall(
                service="bedrock-agent",
                action="startIngestionJob",
                parameters=dataSourceIngestionParams,
                physical_resource_id=cr.PhysicalResourceId.of("Parameter.ARN")
                ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[kb.knowledge_base_arn]
                )
            )
            
            
            #Create DynamoDB table for storing prompts against session-id
        table = dynamodb.TableV2(self, "ChatHistory",
                                partition_key=dynamodb.Attribute(
                                    name="session_id", type=dynamodb.AttributeType.STRING),
                                billing=dynamodb.Billing.on_demand(),
                                removal_policy=RemovalPolicy.DESTROY
                                )
            
        DDB_TABLE = table.table_name
        DDB_ARN = table.table_arn
        
        # Create VPC with public and private subnets
        vpc = ec2.Vpc(self, "StreamlitAppVPC", 
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private", 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,  # Private with NAT Gateway
                    cidr_mask=24
                )
            ]
        )
        
        NagSuppressions.add_resource_suppressions(vpc, [
            {
                "id": "AwsSolutions-VPC7",
                "reason": "Flow logs are not required for the demo"
            }
        ])
        
        # Create Security Group for EC2 in private subnet - allowing only traffic from ALB
        ec2_security_group = ec2.SecurityGroup(self, "EC2SecurityGroup",
            vpc=vpc,
            description="Security group for Streamlit app EC2 instance",
            allow_all_outbound=True
        )
        
        # Create Security Group for ALB - allowing HTTP/HTTPS from CloudFront
        alb_security_group = ec2.SecurityGroup(self, "ALBSecurityGroup",
            vpc=vpc,
            description="Security group for Application Load Balancer",
            allow_all_outbound=True
        )
        alb_security_group.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Allow ALB to connect to EC2 on port 8501
        ec2_security_group.add_ingress_rule(
            alb_security_group,
            ec2.Port.tcp(8501),
            "Allow traffic from ALB to Streamlit port"
        )
        ec2_security_group.apply_removal_policy(RemovalPolicy.DESTROY)
        
        
        alb_security_group.add_ingress_rule(
            ec2.Peer.prefix_list(cloudfront_prefix),  # CloudFront prefix list
            ec2.Port.tcp(80),
            "Allow HTTP from CloudFront to ALB"
        )
        

        # Create IAM role for EC2 instance
        role = iam.Role(self, "StreamlitAppRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
        )
        
        # Add scoped S3 access to specific bucket
        role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:ListBucket"
            ],
            resources=[
                docBucket_arn,
                f"{docBucket_arn}/*",
                policyBucket_arn,
                f"{policyBucket_arn}/*",
                accessLogsBucket_arn,
                f"{accessLogsBucket_arn}/*"
            ]
        ))

        # Add scoped DynamoDB access to specific table
        role.add_to_policy(iam.PolicyStatement(
            actions=[
                "dynamodb:GetItem",
                "dynamodb:PutItem", 
                "dynamodb:UpdateItem"
            ],
            resources=[
                DDB_ARN
            ]
        ))

        # Attach multiple AWS managed policies to the role
        managed_policies = [
            "AmazonBedrockFullAccess",
            "AmazonSSMManagedInstanceCore"
        ]

        for policy_name in managed_policies:
            role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(policy_name))
        
        #Creating Cognito User Pool and App Client
        PARAMETER_COGNITO_USER_POOL_NAME = "Insurance-AI-Assistant-UserPool-" + entryTimestamp
        user_pool = cognito.UserPool(self, PARAMETER_COGNITO_USER_POOL_NAME,
            user_pool_name="Insurance-AI-Assistant-UserPool-" + entryTimestamp,
            self_sign_up_enabled=True,
            advanced_security_mode=cognito.AdvancedSecurityMode.ENFORCED,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            feature_plan=cognito.FeaturePlan.PLUS,
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        user_pool.apply_removal_policy(RemovalPolicy.DESTROY)
        
        PARAMETER_COGNITO_USER_POOL_ID = user_pool.user_pool_id

        app_client = user_pool.add_client("Insurance-AI-Assistant-AppClient-" + entryTimestamp,
            user_pool_client_name="Insurance-AI-Assistant-app-client-" + entryTimestamp,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True
                ),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
            ),
            prevent_user_existence_errors=True
        )
        
        PARAMETER_COGNITO_USER_POOL_CLIENT_ID = app_client.user_pool_client_id
        app_client.apply_removal_policy(RemovalPolicy.DESTROY)
        
        #Reading user_data_script.sh file which contains the linux commands that must be run when the EC2 boots up initially.
        with open("user_data_script.sh", "r", encoding="utf-8") as f:
            user_data_script = f.read()
            
        user_data_script = user_data_script.replace("{{KB_ID}}", KB_ID)
        user_data_script = user_data_script.replace("{{BUCKET_NAME}}", BUCKET_NAME)
        user_data_script = user_data_script.replace("{{DDB_TABLE}}", DDB_TABLE)
        user_data_script = user_data_script.replace("{{MODEL_ID}}", os.environ.get('model_id'))
        user_data_script = user_data_script.replace("$REGION", os.getenv('CDK_DEFAULT_REGION'))
        user_data_script = user_data_script.replace("{{APP_CLIENT_ID}}", PARAMETER_COGNITO_USER_POOL_CLIENT_ID)
        user_data_script = user_data_script.replace("{{USER_POOL_ID}}", PARAMETER_COGNITO_USER_POOL_ID)
        user_data_script = user_data_script.replace("{{GUARDRAIL_ID}}", BEDROCK_GUARDRAIL_ID)
       
        # Create EC2 instance in PRIVATE subnet
        ec2_instance = ec2.Instance(self, "StreamlitAppInstance",
            instance_type=ec2.InstanceType("t2.micro"),
            machine_image=ec2.AmazonLinuxImage(generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),  # Place in private subnet
            security_group=ec2_security_group,
            role=role,
            user_data=ec2.UserData.custom(user_data_script),
            user_data_causes_replacement=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=8,  # Size in GB
                        encrypted=True   # Enable encryption
                    )
                )
            ]
        )
        
        EC2_INSTANCE_ID = ec2_instance.instance_id
        
        NagSuppressions.add_resource_suppressions(ec2_instance, [
            {
                "id": "AwsSolutions-EC28",
                "reason": "For the purposes of demo, EC2 instance detailed monitoring is not required"
            }
        ])
        NagSuppressions.add_resource_suppressions(ec2_instance, [
            {
                "id": "AwsSolutions-EC29",
                "reason": "For the purposes of demo, ASG and termination Protection is not required"
            }
        ])
        
        # Create Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(self, "StreamlitALB",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )
        alb.apply_removal_policy(RemovalPolicy.DESTROY)
        
        instance_target = elasticloadbalancingv2_targets.InstanceTarget(ec2_instance, 8501)
          # Enable access logging after ALB creation
        alb.log_access_logs(
            bucket=accessLogsBucket,
            prefix='alb-logs'  
        )

        # Create ALB target group
        target_group = elbv2.ApplicationTargetGroup(self, "StreamlitTargetGroup",
            vpc=vpc,
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[instance_target],
            health_check=elbv2.HealthCheck(
                path="/",
                port="8501",
                healthy_http_codes="200"
            )
        )
        
        
        # Add listener to ALB
        http_listener = alb.add_listener("HTTPListener",
            port=80,
            default_target_groups=[target_group],
            open=False
        )
        
        
        # Create CloudFront CDN Distribution using ALB as origin
        cdn = cloudfront.Distribution(self, 'CDN', 
            comment='CDK created distribution for Insurance Policy AI Assistant',
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(alb, http_port=80, protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY),
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
            ),
            web_acl_id=web_acl_arn,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021
        )
   
        cdn.apply_removal_policy(RemovalPolicy.DESTROY)
        NagSuppressions.add_resource_suppressions(cdn, [
            {
                "id": "AwsSolutions-CFR1",
                "reason": "For the purposes of demo, Geo restrictions are not required."
            }
        ])
        NagSuppressions.add_resource_suppressions(cdn, [
            {
                "id": "AwsSolutions-CFR3",
                "reason": "For the purposes of demo, Access logging is not required."
            }
        ])
        NagSuppressions.add_resource_suppressions(cdn, [
            {
                "id": "AwsSolutions-CFR4",
                "reason": "For the purposes of demo, no viewer certificate is required."
            }
        ])
        NagSuppressions.add_resource_suppressions(cdn, [
            {
                "id": "AwsSolutions-CFR5",
                "reason": "For the purposes of demo, TLSv1 is only required"
            }
        ])
        
        # Create an IAM role for the Lambda function
        lambda_role = iam.Role(self, "UpdateUserPoolClientRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"))
        
        # Attach managed policy for basic Lambda execution
        lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))

        # Attach custom inline policy for updating user pool client
        lambda_role.add_to_policy(iam.PolicyStatement(
        actions=["cognito-idp:UpdateUserPoolClient"],
        resources=[
            f"arn:aws:cognito-idp:{self.region}:{self.account}:userpool/{PARAMETER_COGNITO_USER_POOL_ID}" 
        ]
        ))

        # (Optional) Add other policies as needed, e.g., to log permissions
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=["*"]
        ))
        
        # Define the Lambda function to update Cognito callback URLs
        lambda_function = _lambda.Function(self, "UpdateCallbackUrlFunction",
            runtime=Runtime.PYTHON_3_12,
            handler="index.handler",
            role=lambda_role,
            code=Code.from_inline("""
import boto3
import os
        
def handler(event, context):
    user_pool_id = event['ResourceProperties']['UserPoolId']
    client_id = event['ResourceProperties']['AppClientId']
    callback_url = event['ResourceProperties']['CallbackUrl']
            
    cognito_client = boto3.client('cognito-idp')
    cognito_client.update_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client_id,
                CallbackURLs=[callback_url]
        )
            
    return {"status": "success"}
    """)
        )
            
        # Create a Custom Resource to trigger the Lambda function
        custom_resource_provider = cr.Provider(self, "UpdateCallbackUrlProvider",
            on_event_handler=lambda_function,
        )
        
        update_callback_url = CustomResource(self, "UpdateCognitoCallbackUrl",
            service_token=custom_resource_provider.service_token,
            properties={
                "UserPoolId": PARAMETER_COGNITO_USER_POOL_ID,
                "AppClientId": PARAMETER_COGNITO_USER_POOL_CLIENT_ID,
                "CallbackUrl": f"https://{cdn.distribution_domain_name}"
            }
        )
        
        # Printing the Cloudfront Distribution Domain Name and Cognito User Pool Name after CDK Deployment
        CfnOutput(
            self, "CloudFront-Distribution-Domain-Name",
            value="https://" + cdn.distribution_domain_name,
            description="The CloudFront Distribution Domain Name"
        )
        CfnOutput(
            self, "Cognito-User-Pool-Name",
            value=PARAMETER_COGNITO_USER_POOL_NAME,
            description="Cognito user pool created at : " + entryTimestamp
        ) 
        CfnOutput(
            self, "ALB-DNS-Name",
            value=alb.load_balancer_dns_name,
            description="Application Load Balancer DNS Name"
        )
        
        # Add dependencies
        dataSource.node.add_dependency(docBucket)
        ingestion_job_cr.node.add_dependency(kb)
        ec2_instance.node.add_dependency(guardrail)
        ec2_instance.node.add_dependency(kb)
        ec2_instance.node.add_dependency(policyBucket)
        ec2_instance.node.add_dependency(table)
        alb.node.add_dependency(ec2_instance)
        http_listener.node.add_dependency(target_group)
        cdn.node.add_dependency(http_listener)
        cdn.node.add_dependency(alb)