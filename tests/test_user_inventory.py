import pytest

from scrapers.user_listings import user_inventory_url


def test_user_inventory_url_first_page():
    assert user_inventory_url("119284386") == (
        "https://www.kleinanzeigen.de/s-bestandsliste.html?"
        "userId=119284386&sortingField=SORTING_DATE"
    )


def test_user_inventory_url_later_page():
    assert user_inventory_url("119284386", 2) == (
        "https://www.kleinanzeigen.de/s-bestandsliste.html?"
        "userId=119284386&sortingField=SORTING_DATE&pageNum=2"
    )


@pytest.mark.parametrize("user_id", ["", "abc", "12/34", "-1"])
def test_user_inventory_rejects_invalid_user_id(user_id):
    with pytest.raises(ValueError):
        user_inventory_url(user_id)


def test_user_inventory_rejects_invalid_page():
    with pytest.raises(ValueError):
        user_inventory_url("119284386", 0)
