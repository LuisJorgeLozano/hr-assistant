Feature: HR Assistant answers questions about employees
  HR staff ask questions and a single agent answers using read-only tools.

  Scenario: Asking for a known employee
    When I ask "Tell me about EMP-0004"
    Then the response status is 200
    And the answer mentions "Jorge"
    And the tools used are "get_employee"

  Scenario: Asking for an employee that does not exist
    When I ask "Tell me about EMP-9999"
    Then the response status is 200
    And the answer mentions "EMP-9999"
    And the tools used are "get_employee"

  Scenario: Asking for a department
    When I ask "Who works in Tecnología?"
    Then the response status is 200
    And the answer mentions "Ana"
    And the tools used are "search_by_department"

  Scenario: Asking something the assistant cannot route
    When I ask "What is the weather today?"
    Then the response status is 200
    And the answer is "Pregúntame por un empleado (EMP-0001) o un departamento."
    And no tools were used

  Scenario: The agent reaches the step limit
    Given a model that never answers and a limit of 3 steps
    When I ask "Tell me about EMP-0001"
    Then the response status is 200
    And the answer is "No pude completar la respuesta. Intenta con una pregunta más concreta."
    And the step count is 3

  Scenario: An empty question is rejected
    When I ask an empty question
    Then the response status is 422

  Scenario: A question longer than the limit is rejected
    Given a question limit of 20 characters
    When I ask a question of 21 characters
    Then the response status is 422

  Scenario: The health endpoint reports the process
    When I request the health endpoint
    Then the response status is 200
    And the health status is "ok" and includes a numeric pid

  Scenario: History is accepted but never kept by the server
    When I ask "Tell me about EMP-0001" with one turn of history
    And I ask "Hello there" without history
    Then the answer is "Pregúntame por un empleado (EMP-0001) o un departamento."

  Scenario: The home page exposes the test ids
    When I request the home page
    Then the response status is 200
    And the page contains the test ids "question", "send" and "answer"
