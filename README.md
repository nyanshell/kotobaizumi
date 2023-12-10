#
## build

```bash

docker build . --progress=plain -t azure-tts:<version>

# debug
docker build . --progress=plain -t azure-tts:<version> 2>&1 | tee build.log
```

## Run

```bash
docker run --env-file=.env -v ./save:/data -it azure-tts:<version>
```

## Config

`.env`:

```
AZURE_SERVICE_TOKEN=<azure-service-token>
OPENAI_API_KEY=<open-api-key>
```