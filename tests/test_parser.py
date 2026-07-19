import unittest

from app.formatter import format_offer
from app.parser import parse_offer


SAMPLE = {
    "id": 1458,
    "label": "G024 STUDIO",
    "area": {"min": 16.0, "max": 18.0},
    "available": True,
    "occupationModes": [{"type": "alone", "rent": {"min": 43000, "max": 43000}}],
    "residence": {
        "label": "Residence Pascal MARTIN",
        "address": "22 avenue Jean Nicoli, BP 55, 20250 CORTE",
        "description": "<p>Résidence située sur le campus</p>",
        "medias": [{"src": "residence/photo test.jpg"}],
    },
    "medias": [],
}


class ParserTests(unittest.TestCase):
    def test_parse_offer(self) -> None:
        offer = parse_offer(SAMPLE, "https://example.test", 47)
        self.assertEqual(offer.offer_id, "1458")
        self.assertEqual(offer.city, "Corte")
        self.assertEqual(offer.postal_code, "20250")
        self.assertEqual(offer.rent, "430.00 €")
        self.assertEqual(offer.surface, "16–18 m²")
        self.assertIn("%20", offer.image_url or "")
        self.assertTrue(offer.official_url.endswith("/tools/47/accommodations/1458"))

    def test_formatter_escapes_html(self) -> None:
        sample = dict(SAMPLE)
        sample["label"] = "Studio <test>"
        offer = parse_offer(sample, "https://example.test", 47)
        message = format_offer(offer)
        self.assertIn("Studio &lt;test&gt;", message)
        self.assertIn("Service indépendant", message)
        self.assertNotIn("Voir l’offre officielle</a>", message)


if __name__ == "__main__":
    unittest.main()
