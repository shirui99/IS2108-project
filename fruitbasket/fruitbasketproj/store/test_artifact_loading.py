import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import joblib
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from .restock import EXPECTED_FEATURES, load_restock_artifacts, predict_restock


class HealthyPipeline:
    def predict(self, row):
        return [5]


class ArtifactLoadingTests(SimpleTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.folder=self.root/'ml_models';self.folder.mkdir()
        self.settings=override_settings(BASE_DIR=self.root);self.settings.enable();self.addCleanup(self.settings.disable)
        load_restock_artifacts.cache_clear();self.addCleanup(load_restock_artifacts.cache_clear)
        self.metadata={'feature_names':EXPECTED_FEATURES,'training_only_category_medians':{'fruit':9},'training_only_overall_median':14}

    def estimate(self):
        return predict_restock(timezone.localdate(),2,'fruit',1,7,history_count=2)

    def write_metadata(self, value):
        (self.folder/'restock_metadata.json').write_text(json.dumps(value))

    def test_healthy_pipeline_is_loaded_once(self):
        self.write_metadata(self.metadata)
        joblib.dump(HealthyPipeline(),self.folder/'restock_model.joblib')
        with patch('store.restock.joblib.load', wraps=joblib.load) as load:
            self.assertEqual((self.estimate()['status'],self.estimate()['interval_days']),('MODEL',5))
            self.assertEqual(load.call_count,1)

    def test_missing_corrupt_and_incompatible_model_keep_valid_metadata(self):
        for kind in ['missing','corrupt','wrong_object','wrong_schema']:
            with self.subTest(kind=kind):
                load_restock_artifacts.cache_clear()
                model=self.folder/'restock_model.joblib'
                if model.exists():model.unlink()
                self.write_metadata({**self.metadata,'feature_names':[]} if kind=='wrong_schema' else self.metadata)
                if kind=='corrupt':model.write_bytes(b'not-a-valid-joblib-file')
                if kind=='wrong_object':joblib.dump({},model)
                result=self.estimate()
                self.assertEqual((result['status'],result['interval_days']),('INITIAL',9))
                self.assertNotIn(str(self.root),result['reason'])
                self.assertNotIn('KeyError',result['reason'])

    def test_unusable_model_without_fallback_is_unavailable(self):
        for metadata in [{**self.metadata,'training_only_category_medians':{},'training_only_overall_median':None}, {**self.metadata,'training_only_category_medians':{'fruit':-1}}, None, []]:
            with self.subTest(metadata=metadata):
                load_restock_artifacts.cache_clear();self.write_metadata(metadata)
                (self.folder/'restock_model.joblib').write_bytes(b'not-a-valid-joblib-file')
                result=self.estimate()
                self.assertEqual((result['status'],result['interval_days'],result['restock_date']),('UNAVAILABLE',None,None))
                self.assertNotIn(str(self.root),result['reason'])
        (self.folder/'restock_metadata.json').unlink();load_restock_artifacts.cache_clear()
        self.assertEqual(self.estimate()['status'],'UNAVAILABLE')
