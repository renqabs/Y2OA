import asyncio
import json
import time
import uuid

import httpx
from fastapi import Request

from .base_adapter import BaseAdapter



class YesAiAdapter(BaseAdapter):
    def __init__(self, password, proxy, api_proxy):
        self.password = password
        self.last_time = None
        if proxy:
            self.proxies = {
                'http://': proxy,
                'https://': proxy,
            }
        else:
            self.proxies = None

        if api_proxy:
            self.api_base = api_proxy
        else:
            self.api_base = 'https://finechatserver.erweima.ai'

    @staticmethod
    def convert_messages_to_prompt(messages):
        content_array = []
        for message in messages:
            content = message["content"]
            content_array.append(content)
        return "\n---------\n".join(content_array)

    def convert_openai_data(self, openai_params):
        # openAI_models = ["gpt-4o"]

        messages = openai_params["messages"]
        prompt = self.convert_messages_to_prompt(messages)
        model: str = openai_params["model"]

        return {
            'prompt': prompt,
            'sessionId': str(uuid.uuid4()).replace('-', '')
        }

    async def chat(self, request: Request):
        openai_params = await request.json()
        headers = request.headers
        stream = openai_params.get("stream")
        model = openai_params.get("model")
        json_data = self.convert_openai_data(openai_params)

        api_key = self.get_request_api_key(headers)
        if api_key != self.password:
            raise Exception(f"Error: 密钥无效")

        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'authorization': '',
            'content-type': 'application/json',
            'origin': 'https://www.yeschat.ai',
            'priority': 'u=1, i',
            'sec-ch-ua': '"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'uniqueid': str(uuid.uuid4()).replace('-', ''),
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0'
        }

        api_url = f'{self.api_base}/api/v1/gpt2/free-gpt2/chat'
        last_text = ""
        last_time = time.time()
        async with httpx.AsyncClient(http2=False, timeout=120.0, verify=False, proxies=self.proxies) as client:
            response = await client.post(url=api_url,headers=headers,json=json_data)
            if response.is_error:
                raise Exception(f"Error: {response.status_code}")

            # print(response.headers)
            if stream:
                yield self.to_openai_response_stream_begin(model=model)
            for raw_data in response.iter_lines():
                if raw_data:
                    # print('raw_data: ' + raw_data)
                    try:
                        text = self.take_text(raw_data)
                    except:
                        print("error!!! ")
                        continue

                    if text == "":
                        continue
                    # print('take text: ' + text)

                    # new_text = text[len(last_text):]
                    last_text = last_text + text
                    if stream:
                        yield self.to_openai_response_stream(model=model, content=text)
                    await self.rate_limit_sleep_async(last_time)
                    last_time = time.time()
            if stream:
                await asyncio.sleep(1)
                yield self.to_openai_response_stream_end(model=model)
                yield "[DONE]"
            else:
                yield self.to_openai_response(model=model, content=last_text)

    @staticmethod
    def take_text(data: json) -> str:
        data_json = json.loads(data)['data']
        if data_json.get("message"):
            return data_json["message"]
        elif data_json.get("url"):
            return f'![]({data_json["url"]})'
        return ""
