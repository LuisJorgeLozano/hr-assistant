Feature: Every answer costs as little as possible without getting worse
  Each cost lever is measured and the cost of every answer is reported.

  Scenario: A simple question goes to the small model and has a cost
    When I ask "Tell me about EMP-0004"
    Then the answer used the small model
    And the route is "simple"
    And the cost is greater than zero

  Scenario: A question that asks for a comparison goes to the large model
    When I ask "Compara las ventas de Ventas y Finanzas"
    Then the answer used the large model
    And the route is "keyword:compara"

  Scenario: With routing off every question goes to the large model
    Given routing is off
    When I ask "Tell me about EMP-0004"
    Then the answer used the large model
    And the route is "routing_off"

  Scenario: A short history window sends fewer input tokens
    Given a conversation history of 10 messages
    When I ask "Tell me about EMP-0004" with a window of 2 and again with a window of 50
    Then the small window used fewer input tokens

  Scenario: The metrics add up the cost of every answer
    When I ask 3 questions
    And I request the metrics
    Then the metrics cost equals the sum of the answer costs

  Scenario: A gateway that is down returns a safe 502
    Given a gateway that is unreachable
    When I ask "Tell me about EMP-0004" with the request id "cost-502"
    Then the response status is 502
    And the error body is "model unavailable" with request id "cost-502"
    And the response does not contain the API token

  Scenario: A call answered from the gateway cache costs nothing
    Given a gateway that answers from its cache
    When I ask "Tell me about EMP-0004"
    Then the response status is 200
    And there is at least 1 cached call
    And the cost is zero
