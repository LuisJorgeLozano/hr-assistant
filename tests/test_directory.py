"""Pruebas unitarias del directorio de empleados."""


def test_known_employee_is_returned(directory):
    employee = directory.get_employee("EMP-0004")
    assert employee["name"] == "Jorge Díaz"
    assert employee["department"] == "Tecnología"


def test_unknown_employee_is_reported(directory):
    assert directory.get_employee("EMP-9999") is None


def test_department_search_ignores_case_and_accents(directory):
    ids = {e["id"] for e in directory.search_by_department("tecnologia")}
    assert ids == {"EMP-0001", "EMP-0003", "EMP-0004"}


def test_department_without_matches_returns_empty_list(directory):
    assert directory.search_by_department("Marketing") == []
