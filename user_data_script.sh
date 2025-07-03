#!/bin/bash
export AWS_DEFAULT_REGION=$REGION
max_attempts=5
attempt_num=1
success=false
#Adding the while loop to ensure all the required modules are installed
while [ $success = false ] && [ $attempt_num -le $max_attempts ]; do
  echo "Trying to install required modules..."
  yum update -y
  yum install -y python3-pip
  yum remove -y python3-requests
  pip3 install boto3 awscli streamlit streamlit-cognito-auth numpy python-dotenv pandas
  # Check the exit code of the command
  if [ $? -eq 0 ]; then
    echo "Installation succeeded!"
    success=true
  else
    echo "Attempt $attempt_num failed. Sleeping for 10 seconds and trying again..."
    sleep 10
    ((attempt_num++))
  fi
done
cat <<EOF > /home/ec2-user/Insurance-AI-Assistant.py
####
import streamlit as st
import random
import time
import json
import boto3
import dotenv
import yaml
import os
import binascii
import base64
from yaml.loader import SafeLoader
from botocore.client import Config
from botocore.exceptions import ClientError
from streamlit_cognito_auth import CognitoAuthenticator
dotenv.load_dotenv()


INIT_MESSAGE = {
    "role": "assistant",
    "content": "Hello there! My name is Felix and I am your Insurance Policy AI Assistant. You can ask me questions regarding your Motor Insurance Policy?",
}

#####Initialising boto3
bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
bedrock_client = boto3.client('bedrock-runtime')
bedrock_agent_client = boto3.client("bedrock-agent-runtime", config=bedrock_config)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('{{DDB_TABLE}}')
bucket_name = "{{BUCKET_NAME}}"
s3 = boto3.client('s3')
cognito = boto3.client('cognito-idp', region_name='$REGION')
pool_id = "{{USER_POOL_ID}}"

app_client_id = "{{APP_CLIENT_ID}}"

#LLM Model
model_id = "{{MODEL_ID}}"

#Bedrock KB ID
kb_id = "{{KB_ID}}"

#Bedrock Guardrail ID
GUARDRAIL_ID = "{{GUARDRAIL_ID}}"
GUARDRAIL_VERSION = "DRAFT"


#Functions 

################################################################################################################
#Cognito authentication flow

authenticator = CognitoAuthenticator(
    pool_id=pool_id,
    app_client_id=app_client_id,
    use_cookies=False
)
is_logged_in = authenticator.login()
if not is_logged_in:
    st.stop()
    
def logout():
    print("Logout in example")
    clear_chat_history()
    st.session_state.messages = [INIT_MESSAGE]
    authenticator.logout()

with st.sidebar:
    st.text(f"Welcome,\n{authenticator.get_username()}")
    st.button("Logout", "logout_btn", on_click=logout)

################################################################################################################
# Creating random session_id using os.urandom
def get_session_id():
    session_id = st.session_state.get("session_id")
    if not session_id:
        # Generate 16 random bytes and convert to hex string
        random_bytes = os.urandom(16)
        session_id = binascii.hexlify(random_bytes).decode('ascii')
        st.session_state["session_id"] = session_id
    return session_id
    
################################################################################################################
#Retrieve Document chunks from Bedrock KB

def retrieve(query, kbId):
    return bedrock_agent_client.retrieve(
        retrievalQuery= {
            'text': query
        },
        knowledgeBaseId=kbId
    )
    
################################################################################################################    
#Fetch text from the response

def get_contexts(retrievalResults):
    contexts = []
    for retrievedResult in retrievalResults: 
        contexts.append(retrievedResult['content']['text'])
    return contexts

################################################################################################################    
#Fetch URIs for citations

def get_uris(retrievalResults):
    uris = []
    for retrievedResult in retrievalResults:
        if 'location' in retrievedResult:
            location = retrievedResult['location']
            if 'type' in location and location['type'] == 'S3':
                if 's3Location' in location:
                    s3_location = location['s3Location']
                    if 'uri' in s3_location:
                        uris.append(s3_location['uri'])
    return list(set(uris))

################################################################################################################
#Parsing generated output stream

def parse_stream(stream):
    for event in stream:
        chunk = event.get('chunk')
        if chunk:
            message = json.loads(chunk.get("bytes").decode())
            if message['type'] == "content_block_delta":
                yield message['delta']['text'] or ""
            elif message['type'] == "message_stop":
                return "\n"

################################################################################################################
#Cleat chat history

def clear_chat_history():
    if "messages" in st.session_state:
        st.session_state.messages = []

################################################################################################################                
#Bedrock Prompt for Claude

def bedrock_prompt(prompt,all_prompts):
    response = retrieve(prompt, kb_id)
    retrievalResults = response['retrievalResults']
    contexts = get_contexts(retrievalResults)
    urisList = get_uris(retrievalResults)
    system_prompt = f"""
    You are a polite and friendly AI Assistant called Felix for a Motor Insurance company called AnyCompany, 
    who can answer questions about motor insurance policies. 
    You are provided with the Customer specific Policy document, 
    as well the General Insurance Policy Documents, which is 
    standard across all customers. Always prioritise the information available in the Customer's Policy over General Insurance Policy Documents.
    This Customer's name is {authenticator.get_username()} and the Customer's Policy is as follows:
    <Policy>
    {policy_details}
    </Policy>
    For this question if there are any relevant information available in the General Insurance Policy Documents, it will be added below, along with citations. 
    
    <context>
    {contexts}
    <citations>
    {urisList}
    </citations>
    </context>
   
   When citing, include only the file names without the S3 bucket name, the "s3://" prefix, or file extensions like ".pdf".
    For example, if the document citations are "s3://test-bucket/keycare_product_information_document.pdf" or "s3://test2-bucket/keycare_policy_booklet.pdf" or "s3://test3-bucket/car_insurance_policy_booklet_11_2023.pdf",
    the citations should be returned as ["Keycare Product Information Document"] or ["Keycare Policy Booklet"] or ["Car Insurance Policy Booklet"] respectively:
    The below given are questions already asked by the customer in this chat session, it can be empty, if not, please consider the below comma separated questions while answering:
    <questions>
    {all_prompts}
    </questions>
    Answer only based on the Customer specific Policy and General Insurance Policy Documents. Any information outside these documents should be omitted. 
    If you have used any information from the General Insurance Policy Documents, add citations. 
    Include page number or section number/names of the documents to the citations only when this information is available from the above context. Only cite page numbers that explicitly appear in the context.
    When the Customer needs to contact the insurance provider for more information, direct them to email insurance-queries@anycompany.com. 
    Provide the response in a user-friendly manner so that it is easy to read. Always refer to yourself and AnyCompany in first person.
    """
    
    
    body = json.dumps({
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 10000,
    "system": system_prompt,
    "messages": [
        {
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }
    ],
    "amazon-bedrock-guardrailConfig": {"streamProcessingMode": "ASYNCHRONOUS"}
    })
    return body

############################################################################################################################################
#Fetching private policy doc directly from S3

def user_policy(username):
    object_key = f'{username}.txt'
    try:
        response_s3 = s3.get_object(Bucket=bucket_name, Key=object_key)
        # Read the contents of the file
        text = response_s3['Body'].read().decode('utf-8')
        return text
        
    except Exception as e:
        return "No insurance policy found for the customer"


############################################################################################################################################
def dynamodb_prompts(prompt, session_id):
# First, check if the prompt already exists
    response_get = table.get_item(
    Key={
                'session_id': session_id,
                
            }
        )
    if 'Item' in response_get:
        #print("existing_session")
        existing_prompt = response_get['Item']['prompt']
        all_prompts = existing_prompt + "," + prompt
        response = table.update_item(
            Key={
                'session_id':session_id
                
            },
            UpdateExpression="set prompt=:p",
            ExpressionAttributeValues={
                ':p':all_prompts
            },
            ReturnValues="UPDATED_NEW"
            )
        return all_prompts
    else:
        #print("new_session")
        response = table.put_item(
        Item={
                    'session_id': session_id,
                    'prompt': prompt
        })
        all_prompts = ""
        return all_prompts


############################################################################################################################################

authenticator.login()    

if is_logged_in:
    username = authenticator.get_username()
    policy_details = user_policy(username)
    st.title("Insurance Policy AI Assistant")

    # Get the session ID
    session_id = get_session_id()
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = [INIT_MESSAGE]

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
 
    #st.session_state.messages.append({"role": "assistant", "content": greeting})
    
    # Accept user input
    if prompt := st.chat_input("Enter your question about your motor insurance policy:"):
        
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        all_prompts = dynamodb_prompts(prompt, session_id)
        
        with st.chat_message("assistant"):
            claude_body = bedrock_prompt(prompt,all_prompts) #Calling the function
            streaming_response = bedrock_client.invoke_model_with_response_stream(
            modelId=model_id,
            body=claude_body,
            contentType="application/json",
            accept="application/json",
            guardrailIdentifier= GUARDRAIL_ID,
            guardrailVersion= GUARDRAIL_VERSION
            )
            stream = streaming_response.get("body")
            # Use st.empty() to reduce flickering
            response_container = st.empty()
            full_response = ""

            for chunk in parse_stream(stream):
                full_response += chunk
                response_container.markdown(full_response)

        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": full_response})
else:
      clear_chat_history()
      prompt = ""
      all_prompts = ""
     
     # Reset session_id by clearing it first from session state (if it exists)
      if "session_id" in st.session_state:
        del st.session_state["session_id"]
    
    # Call get_session_id() to generate a new session ID
      session_id = get_session_id()
      st.session_state["messages"] = [INIT_MESSAGE]
EOF
# Ensure working directory is set to the location of the files
cd /home/ec2-user
#Run the streamlit app in the background
nohup streamlit run /home/ec2-user/Insurance-AI-Assistant.py &
