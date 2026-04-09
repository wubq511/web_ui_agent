import asyncio
import json
import tempfile
import unittest
from pathlib import Path


class CustomOnlyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_path = Path(self.temp_dir.name)

    def _install_temp_store(self):
        import llm_config_store
        import web_server

        store = llm_config_store.LLMConfigStore(data_dir=self.base_path)
        llm_config_store._store_instance = store
        web_server.llm_config_store = store
        return store

    def test_agent_start_rejects_when_no_custom_model_even_if_env_exists(self) -> None:
        import os
        import web_server

        self._install_temp_store()
        os.environ["LINGYAAI_API_KEY"] = "fake-env-key"
        self.addCleanup(lambda: os.environ.pop("LINGYAAI_API_KEY", None))

        web_server.agent_state.status = "idle"
        response = asyncio.run(
            web_server.start_agent(
                web_server.StartAgentRequest(objective="test", model="")
            )
        )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body.decode("utf-8"))
        self.assertIn("当前没有可用的自定义模型配置", payload["message"])

    def test_model_manager_never_switches_to_removed_builtin_target(self) -> None:
        import llm_config_store
        import model_manager

        store = self._install_temp_store()
        created = store.create_config(
            display_name="Only Custom",
            provider="openai-compatible",
            model_name="custom-model",
            base_url="https://example.com/v1",
            api_key="sk-custom-secret",
        )

        llm_config_store._store_instance = store
        manager = model_manager.ModelManager(api_key=None)
        manager.set_initial_model(created["id"])

        switched = False
        for _ in range(3):
            switched = manager.record_failure(created["id"])

        self.assertFalse(switched)
        self.assertEqual(manager.get_current_model(), created["id"])


if __name__ == "__main__":
    unittest.main()
