Feature: Every request can be traced from its request id
  Support can answer what happened to a request using the log and the metrics.

  Scenario: A request id is generated when the client sends none
    When I ask "Tell me about EMP-0004" without a request id
    Then the response status is 200
    And the X-Request-ID header is a generated UUID
    And the body request_id equals the X-Request-ID header

  Scenario: The client request id is respected
    When I ask "Tell me about EMP-0004" with the request id "support-123"
    Then the X-Request-ID header is "support-123"
    And the body request_id is "support-123"

  Scenario: One question leaves request, agent_run and audit lines without personal text
    Given each model call takes 50 ms
    When I ask "Tell me about EMP-0004 for the annual review" with the request id "trace-1"
    Then the log has a "request" line for "trace-1" with status 200 and latency 100 ms
    And the log has an "agent_run" line for "trace-1"
    And the log has an "audit" line for "trace-1" with tool "get_employee"
    And the log does not contain the question or the answer

  Scenario: A model failure returns an internal error with the request id
    Given a model that always fails
    When I ask "Tell me about EMP-0004" with the request id "boom-1"
    Then the response status is 500
    And the error body is "internal error" with request id "boom-1"
    And the log has an "error" line for "boom-1" with type "RuntimeError"
    And the log does not contain "secret failure detail"

  Scenario Outline: Metrics report the process and the latency target
    Given each model call takes 100 ms
    And a latency target of <target> ms
    When I ask 2 questions
    And I request the metrics
    Then the metrics show 2 requests and no errors
    And the metrics show tokens and a p95 of 100 ms
    And the latency target is met: <met>

    Examples:
      | target | met   |
      | 500    | true  |
      | 50     | false |

  Scenario: The home page shows the request id of each answer
    When I request the home page
    Then the page has a place for the request id
