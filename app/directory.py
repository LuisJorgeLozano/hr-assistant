"""Directorio de empleados de solo lectura."""
import json
import unicodedata
from pathlib import Path


def normalize(text: str) -> str:
    """Pasa a minusculas y quita acentos para comparar.

    :param text: texto original
    :return: texto normalizado
    """
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class Directory:
    """Empleados cargados desde un archivo JSON.

    :param path: ruta del archivo de empleados
    """

    def __init__(self, path):
        with open(Path(path), encoding="utf-8") as handle:
            self._employees = json.load(handle)

    @property
    def departments(self) -> list:
        """Nombres de departamento presentes en los datos.

        :return: lista sin repetidos
        """
        return sorted({e["department"] for e in self._employees})

    def get_employee(self, employee_id: str):
        """Busca un empleado por id.

        :param employee_id: id, por ejemplo ``EMP-0004``
        :return: el empleado o ``None`` si no existe
        """
        for employee in self._employees:
            if employee["id"] == employee_id:
                return dict(employee)
        return None

    def search_by_department(self, department: str) -> list:
        """Lista los empleados de un departamento.

        :param department: nombre, sin distinguir mayusculas ni acentos
        :return: lista de empleados (vacia si no hay coincidencias)
        """
        wanted = normalize(department)
        return [
            dict(e) for e in self._employees if normalize(e["department"]) == wanted
        ]
