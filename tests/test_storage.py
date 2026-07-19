import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.models import Offer
from app.storage import OfferStore


def offer(offer_id: str = "1") -> Offer:
    return Offer(
        offer_id=offer_id,
        title="Studio",
        residence="Résidence Test",
        city="Rouen",
        postal_code="76000",
        housing_type="Studio",
        rent="400.00 €",
        charges=None,
        surface="18 m²",
        availability_date=None,
        short_description=None,
        image_url=None,
        official_url="https://example.test/offer/1",
        content_hash="abc",
    )


class StorageTests(unittest.TestCase):
    def test_deduplication_and_reactivation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with OfferStore(Path(directory) / "offers.sqlite3") as store:
                self.assertEqual(
                    [item.offer_id for item in store.apply_scan([offer()])], ["1"]
                )
                self.assertEqual(store.apply_scan([offer()]), [])
                store.apply_scan([])
                self.assertEqual(
                    [item.offer_id for item in store.apply_scan([offer()])], ["1"]
                )

    def test_database_url_takes_priority_on_hosted_service(self) -> None:
        with patch.dict(
            environ,
            {
                "DATABASE_URL": "postgresql://example.invalid/database",
                "DATABASE_PATH": "data/local.sqlite3",
            },
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(
            settings.database_target, "postgresql://example.invalid/database"
        )


if __name__ == "__main__":
    unittest.main()
