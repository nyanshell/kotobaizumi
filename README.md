# 言葉の泉

## build

```bash

docker build . --progress=plain -t kotoba:<version>

# debug
docker build . --progress=plain -t kotoba:<version> 2>&1 | tee build.log
```

## Run

docker:

```bash
docker run --env-file=.env -p 0.0.0.0:5000:5000 -v ./save:/data -it kotoba:<version>
```

### Debug run

```bash
dotenv run -- flask --app app/app.py run --debug
```

## Config

`.env`:

```
AZURE_SERVICE_TOKEN=<azure-service-token>
OPENAI_API_KEY=<open-api-key>
```

## To-Do

- Jump to the generated card after created.
- Support Gemini for the grammar explain
- Fix: memory graph, play time.
- Add Azure's DrangonHD audio model.
- Showing total statics
- Detail toggle for each grammar point.
- Play whole results.
- Exercise mode, filling in the blank(grammar point).
  ```
  e.g.
  Question: __朝ごはんを食べました。(<button-play-audio>)
  Answer: しっかり
  ```
- Add exercise: Listening
  ```
  e.g.
  Question: <play-audio>
  Answer: ___
  ```
- github workflow for CI
