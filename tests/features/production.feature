Feature: The product is safe to publish
  Only clients with a key can ask questions, nobody can flood the service and an
  unsafe production setup never starts.

  Scenario: Protected routes reject a request without a key
    When I send "POST /ask" without a key
    Then the response is 401 with the detail "invalid or missing API key"
    When I send "GET /metrics" without a key
    Then the response is 401 with the detail "invalid or missing API key"

  Scenario: A wrong key is rejected and a valid key is accepted
    When I send "POST /ask" with the key "wrong-key-that-nobody-owns"
    Then the response is 401 with the detail "invalid or missing API key"
    When I send "POST /ask" with the key of "acme"
    Then the response status is 200

  Scenario: The home page, the health check and the docs need no key
    When I send "GET /" without a key
    Then the response status is 200
    When I send "GET /health" without a key
    Then the response status is 200
    When I send "GET /docs" without a key
    Then the response status is 200

  Scenario: The client name is logged and the key never is
    When I ask "Tell me about EMP-0004" as "acme" with the request id "audit-1"
    Then the "request" log line for "audit-1" has the client "acme"
    And the "agent_run" log line for "audit-1" has the client "acme"
    And the "audit" log line for "audit-1" has the client "acme"
    When I send "POST /ask" with the key "wrong-key-that-nobody-owns"
    Then no key appears in the log or in any response

  Scenario: A client that passes the limit is told how long to wait
    Given a limit of 3 requests per minute
    When I ask 3 questions as "acme"
    Then the response status is 200
    When I ask 1 questions as "acme"
    Then the response is 429 with the detail "rate limit exceeded"
    And the Retry-After header is a number of seconds up to 60
    When one minute and one second passes
    And I ask 1 questions as "acme"
    Then the response status is 200

  Scenario: Each client has its own limit
    Given a limit of 1 requests per minute
    When I ask 2 questions as "acme"
    Then the response status is 429
    When I ask 1 questions as "globex"
    Then the response status is 200

  Scenario Outline: Production refuses to start with an unsafe setup
    Given a production setup with <problem>
    When I start the product
    Then it refuses to start and the message names "<rule>"
    And the message does not contain any API key

    Examples:
      | problem                   | rule           |
      | the fake model            | MODEL_PROVIDER |
      | no API keys               | API_KEYS       |
      | a key shorter than 16     | API_KEYS       |
      | traces that show inputs   | HIDE_INPUTS    |

  Scenario: A malformed API_KEYS prevents startup without revealing the entry
    When I load the configuration with API_KEYS "acme:long-enough-key-123,secretwithoutcolon"
    Then it refuses to start and the message names "API_KEYS"
    And the message names "entry 2" and "length 18"
    And the message does not contain "secretwithoutcolon"
