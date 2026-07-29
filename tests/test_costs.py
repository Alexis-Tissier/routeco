from app.services.costs import calculate_costs


def test_twingo_costs():
    result = calculate_costs(300, 200, 6.5, 5.5, 1.82, 20)
    assert result.fuel_liters == 30.5
    assert result.fuel_cost == 55.51
    assert result.total_cost == 75.51

# ROUTECO_V034_COST_ROUNDING_FOLLOWUP
def test_total_equals_displayed_fuel_plus_toll_at_half_cent_boundary() -> None:
    result = calculate_costs(229.1, 324.7, 6.5, 5.5, 1.82, 23.40)

    assert result.fuel_cost == 59.61
    assert result.total_cost == 83.01
    assert result.total_cost == round(result.fuel_cost + 23.40, 2)
