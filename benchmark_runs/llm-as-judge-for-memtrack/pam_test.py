from openai import OpenAI

API_KEY = "3h5kMz9XAASDaqYjJz90zu6e97DXkJ9Q0NEuFt45uV1hIydka0LsJQQJ99BKAC5T7U2XJ3w3AAABACOGmnZi"

endpoint = "https://pam-benchmark.cognitiveservices.azure.com/openai/v1/"
model_name = "gpt-4.1"
deployment_name = "gpt-4.1"

client = OpenAI(
    base_url=endpoint,
    api_key=API_KEY,
)

completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": "What is the capital of France?",
        }
    ],
)

print(completion.model_dump_json(indent=2))