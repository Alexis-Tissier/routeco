from app.services.costs import calculate_costs


def test_twingo_costs():
    result = calculate_costs(300, 200, 6.5, 5.5, 1.82, 20)
    assert result.fuel_liters == 30.5
    assert result.fuel_cost == 55.51
    assert result.total_cost == 75.51
