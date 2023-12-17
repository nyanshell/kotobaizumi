# 言葉の泉

## build

```bash

docker build . --progress=plain -t azure-tts:<version>

# debug
docker build . --progress=plain -t azure-tts:<version> 2>&1 | tee build.log
```

## Run

```bash
docker run --env-file=.env -p 0.0.0.0:5000:5000 -v ./save:/data -it azure-tts:<version>
```

## Config

`.env`:

```
AZURE_SERVICE_TOKEN=<azure-service-token>
OPENAI_API_KEY=<open-api-key>
```

## To-Do

- [DONE] ~~Add grammar explanation.~~
- [DONE] ~~Add sentence reading.~~
- [DONE] ~~Support delete.~~
- [DONE] ~~Choose by frequency.~~
- [DONE] ~~Loop mode.~~
- Merge json meta file and sql?
