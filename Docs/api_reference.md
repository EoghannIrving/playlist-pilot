# API Reference

All programmatic endpoints are versioned under `/api/v1`.

| Method | Path | Description |
|-------|------|-------------|
| GET | `/api/v1/health` | Simple health check |
| GET | `/api/v1/integration-failures` | Current integration failure counters |
| POST | `/api/v1/test/lastfm` | Verify Last.fm connectivity |
| POST | `/api/v1/test/jellyfin` | Verify Jellyfin connectivity |
| POST | `/api/v1/test/openai` | Verify OpenAI connectivity |
| POST | `/api/v1/test/getsongbpm` | Verify GetSongBPM connectivity |
| POST | `/api/v1/verify-entry` | Verify a playlist entry ID |

## Example Requests

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Verify Jellyfin
```bash
curl -X POST http://localhost:8000/api/v1/test/jellyfin \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://jellyfin.local","key":"API_KEY"}'
```

## Authentication

Endpoints do not require authentication by default. Use a reverse proxy or custom middleware if your deployment needs protection.

## OpenAPI schema

```json
{
  "openapi": "3.1.0",
  "paths": {
    "/api/v1/test/lastfm": {
      "post": {
        "tags": [
          "Testing"
        ],
        "summary": "Test Lastfm",
        "description": "Validate a Last.fm API key by performing a simple artist search.",
        "operationId": "test_lastfm_api_v1_test_lastfm_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/LastfmTestRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/LastfmTestResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/test/jellyfin": {
      "post": {
        "tags": [
          "Testing"
        ],
        "summary": "Test Jellyfin",
        "description": "Verify the provided Jellyfin URL and API key.",
        "operationId": "test_jellyfin_api_v1_test_jellyfin_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/JellyfinTestRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/JellyfinTestResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/test/openai": {
      "post": {
        "tags": [
          "Testing"
        ],
        "summary": "Test Openai",
        "description": "Check if the OpenAI API key is valid by listing available models.",
        "operationId": "test_openai_api_v1_test_openai_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/OpenAITestRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OpenAITestResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/test/getsongbpm": {
      "post": {
        "tags": [
          "Testing"
        ],
        "summary": "Test Getsongbpm",
        "description": "Check if the GetSongBPM API key is valid by performing a sample query.",
        "operationId": "test_getsongbpm_api_v1_test_getsongbpm_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/GetSongBPMTestRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/GetSongBPMTestResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/verify-entry": {
      "post": {
        "tags": [
          "Jellyfin"
        ],
        "summary": "Verify Playlist Entry",
        "description": "Confirm that a playlist contains the specified entry ID.",
        "operationId": "verify_playlist_entry_api_v1_verify_entry_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/VerifyEntryRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/VerifyEntryResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/health": {
      "get": {
        "tags": [
          "System"
        ],
        "summary": "Health Check",
        "description": "Simple endpoint for container liveness monitoring.",
        "operationId": "health_check_api_v1_health_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HealthResponse"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/integration-failures": {
      "get": {
        "tags": [
          "Monitoring"
        ],
        "summary": "Integration Failures",
        "description": "Return current integration failure counters.",
        "operationId": "integration_failures_api_v1_integration_failures_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/IntegrationFailuresResponse"
                }
              }
            }
          }
        }
      }
    }
  }
}
```
