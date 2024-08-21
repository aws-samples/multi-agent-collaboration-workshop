# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import json
import boto3

bedrock_agent_client = boto3.client('bedrock-agent')
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime')

# Prepare a dictionary of function names and agent id's based on 
# the agent id list in the evironment variable. Makes this Lambda function
# reusable as a Supervisor Agent implementation for any collection of sub agents.

import os
ID_LIST_STR = os.getenv('SUB_AGENT_IDS')

ID_LIST = ID_LIST_STR.split(",")
ID_LIST = [id.strip() for id in ID_LIST]
SUB_AGENT_IDS = {}
for id in ID_LIST:
    print(id)
    resp = bedrock_agent_client.get_agent(agentId=id)
    agent_name = resp['agent']['agentName']
    print(agent_name)
    function = f"invoke-{agent_name}"
    SUB_AGENT_IDS[function] = id
print(f"sub-agents used by this Supervisor agent: {SUB_AGENT_IDS}")


def invoke_sub_agent(query, session_id, agent_id, alias_id='TSTALIASID', 
                enable_trace=False, session_state=dict()):

    end_session:bool = False
    
    # invoke the agent API
    agentResponse = bedrock_agent_runtime_client.invoke_agent(
        inputText=query,
        agentId=agent_id,
        agentAliasId=alias_id, 
        sessionId=session_id,
        enableTrace=enable_trace, 
        endSession= end_session,
        sessionState=session_state
    )
    
    if enable_trace:
        logger.info(pprint.pprint(agentResponse))
    
    event_stream = agentResponse['completion']
    try:
        for event in event_stream:        
            if 'chunk' in event:
                data = event['chunk']['bytes']
                if enable_trace:
                    logger.info(f"Final answer ->\n{data.decode('utf8')}")
                agent_answer = data.decode('utf8')
                end_event_received = True
                return agent_answer
                # End event indicates that the request finished successfully
            elif 'trace' in event:
                if enable_trace:
                    logger.info(json.dumps(event['trace'], indent=2))
            else:
                raise Exception("unexpected event.", event)
    except Exception as e:
        raise Exception("unexpected event.", e)

def get_named_parameter(event, name):
    return next(item for item in event['parameters'] if item['name'] == name)['value']
    
def populate_function_response(event, response_body):
    return {'response': {'actionGroup': event['actionGroup'], 'function': event['function'],
                'functionResponse': {'responseBody': {'TEXT': {'body': str(response_body)}}}}}

def lambda_handler(event, context):
    print(event)
    
    function = event['function']
    session_id = event['sessionId']

    if function in SUB_AGENT_IDS:
        input_text = get_named_parameter(event, 'input_text')
        if not input_text:
            raise Exception("Missing mandatory parameter: input_text")
            
        print(f"Invoking sub-agent: {function.split('invoke-')[1]}...")
        sess_attrs = event['sessionAttributes']
        prompt_attrs = event['promptSessionAttributes']
        result = invoke_sub_agent(input_text, session_id, SUB_AGENT_IDS[function],
                    session_state =
                        {"sessionAttributes": {} if sess_attrs is None else sess_attrs,
                         "promptSessionAttributes": {} if prompt_attrs is None else prompt_attrs})
    else:
        raise Exception(f"Unrecognized function: {function}")

    response = populate_function_response(event, result)
    print(response)
    return response
