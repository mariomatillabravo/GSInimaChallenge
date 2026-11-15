"""Integration tests for the stations endpoint and the OpenAPI document."""

from fastapi.testclient import TestClient


def test_stations_are_listed_with_their_local_time(client: TestClient) -> None:
    response = client.get("/api/v1/stations")

    assert response.status_code == 200
    stations = {station["id"]: station for station in response.json()}
    assert set(stations) == {"juan-carlos-i", "gabriel-de-castilla"}
    assert stations["gabriel-de-castilla"]["aemet_id"] == "89070"
    assert stations["juan-carlos-i"]["timezone"] == "UTC-03:00"


def test_openapi_document_describes_the_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    measurements = paths["/api/v1/stations/{station_id}/measurements"]["get"]
    assert {"404", "422", "502", "503", "504"} <= set(measurements["responses"])
    assert "/api/v1/stations" in paths
