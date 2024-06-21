package main

import (
    "github.com/valyala/fasthttp"
    "time"
    "fmt"
    "strings"
)

func main() {
    handler := func(ctx *fasthttp.RequestCtx) {
        path := string(ctx.Path())

        if matched, _ := pathMatch("/benchmark/model/*/converse", path); matched {
            rootHandler(ctx)
        } else if path == "/benchmark/health" {
            healthCheckHandler(ctx)
        } else {
            ctx.Error("Unsupported path", fasthttp.StatusNotFound)
        }
    }

    fasthttp.ListenAndServe(":8080", handler)
}

func pathMatch(pattern, path string) (bool, error) {
    splitPattern := strings.Split(pattern, "*")
    if len(splitPattern) != 2 {
        return false, fmt.Errorf("pattern must contain exactly one wildcard")
    }

    prefix := splitPattern[0]
    suffix := splitPattern[1]

    return strings.HasPrefix(path, prefix) && strings.HasSuffix(path, suffix), nil
}

func rootHandler(ctx *fasthttp.RequestCtx) {
    // Simulate some delay
    time.Sleep(4 * time.Second)

    // Set content type to JSON
    ctx.SetContentType("application/json")

    // Return an empty JSON object
    ctx.SetBodyString(`{
        "output": {
            "message": {
                "content": [
                    {
                        "text": "test text"
                    }
                ],
                "role": "assistant"
            }
        },
        "additionalModelResponseFields": {
            "stop_sequence": "SUCCESS"
        },
        "stopReason": "stop_sequence",
        "usage": {
            "inputTokens": 51,
            "outputTokens": 442,
            "totalTokens": 493
        },
        "metrics": {
            "latencyMs": 7944
        }
    }`)
}

func healthCheckHandler(ctx *fasthttp.RequestCtx) {
    // Respond with HTTP 200 OK and a simple message
    ctx.SetStatusCode(fasthttp.StatusOK)
    ctx.SetContentType("application/json")
    ctx.SetBodyString(`{"status": "healthy"}`)
}
