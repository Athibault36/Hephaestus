# Cursor + NVIDIA NIM models

`.~cursorconfig.json` documents Hephaestus NIM models for this repo. **Cursor does not auto-import models from this file** into the model picker — add them once in Cursor Settings.

## Add DeepSeek V4 Pro (one-time)

1. Open **Cursor Settings** (`Ctrl+Shift+J`)
2. Go to **Models**
3. Enable **OpenAI API Key** → paste your `NVIDIA_API_KEY` (`nvapi-...`)
4. Enable **Override OpenAI Base URL** → `https://integrate.api.nvidia.com/v1`
5. Click **+ Add model** and type exactly:
   ```
   deepseek-ai/deepseek-v4-pro-0813
   ```
6. Enable the checkbox next to the new model
7. Select it in the chat/agent model dropdown

Optional fast coder (same base URL + key):

```
nvidia/nemotron-3.5-lightning-30b-a3b
```

## Notes

- **Refresh model list** does not discover NIM models — add IDs manually.
- Use a **unique display name** if a built-in model conflicts (e.g. don't name a custom model `gpt-4`).
- Open the **Hephaestus** folder (`C:\dev\Hephaestus`) when working on forge/bridge — config lives in that repo root.
- Copy `.~cursorconfig.json.example` → `.~cursorconfig.json` on new machines (gitignored).

## Verify NIM key

```powershell
$env:NVIDIA_API_KEY = "nvapi-..."
python -c "
from openai import OpenAI
import os
c = OpenAI(base_url='https://integrate.api.nvidia.com/v1', api_key=os.environ['NVIDIA_API_KEY'])
r = c.chat.completions.create(model='deepseek-ai/deepseek-v4-pro-0813', messages=[{'role':'user','content':'ping'}], max_tokens=16, extra_body={'chat_template_kwargs':{'thinking':False}})
print(r.choices[0].message.content)
"
```
