import json
import tempfile
import unittest
from pathlib import Path


class LLMConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_path = Path(self.temp_dir.name)

    def _create_store(self):
        from llm_config_store import LLMConfigStore

        return LLMConfigStore(data_dir=self.base_path)

    def test_create_config_encrypts_api_key_and_merges_model_catalog(self) -> None:
        store = self._create_store()

        self.assertEqual(store.get_available_models(include_secrets=True), {})

        created = store.create_config(
            display_name="OpenRouter",
            provider="openai-compatible",
            model_name="openai/gpt-4o-mini",
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test-openrouter-secret",
            supports_vision=True,
            max_tokens=16384,
        )

        listed = store.list_configs()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], created["id"])
        self.assertEqual(listed[0]["display_name"], "OpenRouter")
        self.assertNotIn("api_key", listed[0])
        self.assertIn("api_key_masked", listed[0])
        self.assertNotEqual(listed[0]["api_key_masked"], "sk-test-openrouter-secret")

        raw_store = (self.base_path / "llm_provider_configs.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("sk-test-openrouter-secret", raw_store)

        merged = store.get_available_models(include_secrets=True)
        self.assertEqual(set(merged.keys()), {created["id"]})
        self.assertEqual(merged[created["id"]]["runtime_model"], "openai/gpt-4o-mini")
        self.assertEqual(
            merged[created["id"]]["api_base"], "https://openrouter.ai/api/v1"
        )
        self.assertEqual(merged[created["id"]]["api_key"], "sk-test-openrouter-secret")
        self.assertTrue(merged[created["id"]]["supports_vision"])

    def test_update_and_delete_config(self) -> None:
        store = self._create_store()

        created = store.create_config(
            display_name="Moonshot",
            provider="openai-compatible",
            model_name="moonshot-v1-8k",
            base_url="https://api.moonshot.cn/v1",
            api_key="sk-test-moonshot-secret",
        )

        updated = store.update_config(
            created["id"],
            display_name="Moonshot Kimi",
            model_name="moonshot-v1-32k",
            api_key="sk-test-moonshot-updated",
        )

        self.assertEqual(updated["display_name"], "Moonshot Kimi")

        merged = store.get_available_models(include_secrets=True)
        self.assertEqual(set(merged.keys()), {created["id"]})
        self.assertEqual(merged[created["id"]]["runtime_model"], "moonshot-v1-32k")
        self.assertEqual(merged[created["id"]]["api_key"], "sk-test-moonshot-updated")

        deleted = store.delete_config(created["id"])
        self.assertTrue(deleted)
        self.assertEqual(store.list_configs(), [])
        self.assertNotIn(
            created["id"], store.get_available_models(include_secrets=True)
        )


if __name__ == "__main__":
    unittest.main()
