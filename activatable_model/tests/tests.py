from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_syncdb
from django.test import TestCase, TransactionTestCase
from django_dynamic_fixture import G
from mock import patch, MagicMock

from activatable_model import BaseActivatableModel, model_activations_changed
from activatable_model.models import get_activatable_models
from activatable_model.tests.models import ActivatableModel, ActivatableModelWRel, Rel


class BaseMockActivationsSignalHanderTest(TestCase):
    """
    Connects a mock to the model_activations_changed signal so that it can be easily tested.
    """
    def setUp(self):
        super(BaseMockActivationsSignalHanderTest, self).setUp()
        self.mock_model_activations_changed_handler = MagicMock()
        model_activations_changed.connect(self.mock_model_activations_changed_handler)

    def tearDown(self):
        super(BaseMockActivationsSignalHanderTest, self).tearDown()
        model_activations_changed.disconnect(self.mock_model_activations_changed_handler)


class NoCascadeTest(TransactionTestCase):
    """
    Tests that cascade deletes cant happen on an activatable test model.
    """
    def test_no_cascade(self):
        rel = G(Rel)
        G(ActivatableModelWRel, rel_field=rel)
        with self.assertRaises(models.ProtectedError):
            rel.delete()


class ManagerQuerySetTest(BaseMockActivationsSignalHanderTest):
    """
    Tests custom functionality in the manager and queryset for activatable models.
    """
    def test_update_no_is_active(self):
        G(ActivatableModel, is_active=False)
        G(ActivatableModel, is_active=False)
        ActivatableModel.objects.update(char_field='hi')
        self.assertEquals(ActivatableModel.objects.filter(char_field='hi', is_active=False).count(), 2)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 2)

    def test_update_w_is_active(self):
        m1 = G(ActivatableModel, is_active=False)
        m2 = G(ActivatableModel, is_active=False)
        ActivatableModel.objects.update(char_field='hi', is_active=True)
        self.assertEquals(ActivatableModel.objects.filter(char_field='hi', is_active=True).count(), 2)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 3)

        call_args = self.mock_model_activations_changed_handler.call_args
        self.assertEquals(call_args[1]['is_active'], True)
        self.assertEquals(set(call_args[1]['instances']), set([m1, m2]))
        self.assertEquals(call_args[1]['sender'], ActivatableModel)

    def test_activate(self):
        G(ActivatableModel, is_active=False)
        G(ActivatableModel, is_active=True)
        ActivatableModel.objects.activate()
        self.assertEquals(ActivatableModel.objects.filter(is_active=True).count(), 2)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 3)

    def test_deactivate(self):
        G(ActivatableModel, is_active=False)
        G(ActivatableModel, is_active=True)
        ActivatableModel.objects.deactivate()
        self.assertEquals(ActivatableModel.objects.filter(is_active=False).count(), 2)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 3)

    def test_delete_no_force(self):
        G(ActivatableModel, is_active=False)
        G(ActivatableModel, is_active=True)
        ActivatableModel.objects.all().delete()
        self.assertEquals(ActivatableModel.objects.filter(is_active=False).count(), 2)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 3)

    def test_delete_w_force(self):
        G(ActivatableModel, is_active=False)
        G(ActivatableModel, is_active=True)
        ActivatableModel.objects.all().delete(force=True)
        self.assertFalse(ActivatableModel.objects.exists())
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 2)


class SaveTest(BaseMockActivationsSignalHanderTest):
    """
    Tests the custom save function in the BaseActivatableModel.
    """
    def test_create(self):
        m = G(ActivatableModel, is_active=False)
        call_args = self.mock_model_activations_changed_handler.call_args
        self.assertEquals(call_args[1]['is_active'], False)
        self.assertEquals(call_args[1]['instances'], [m])
        self.assertEquals(call_args[1]['sender'], ActivatableModel)

    def test_save_not_changed(self):
        m = G(ActivatableModel, is_active=False)
        m.is_active = False
        m.save()

        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 1)

    def test_save_changed(self):
        m = G(ActivatableModel, is_active=False)
        m.is_active = True
        m.save()

        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 2)
        call_args = self.mock_model_activations_changed_handler.call_args
        self.assertEquals(call_args[1]['is_active'], True)
        self.assertEquals(call_args[1]['instances'], [m])
        self.assertEquals(call_args[1]['sender'], ActivatableModel)


class SingleDeleteTest(BaseMockActivationsSignalHanderTest):
    """
    Tests calling delete on a single model that inherits BaseActivatableModel.
    """
    def test_delete_no_force_no_active_changed(self):
        m = G(ActivatableModel, is_active=False)
        m.delete()
        m = ActivatableModel.objects.get(id=m.id)
        self.assertFalse(m.is_active)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 1)

    def test_delete_no_force_active_changed(self):
        m = G(ActivatableModel, is_active=True)
        m.delete()
        m = ActivatableModel.objects.get(id=m.id)
        self.assertFalse(m.is_active)
        self.assertEquals(self.mock_model_activations_changed_handler.call_count, 2)

    def test_delete_force(self):
        m = G(ActivatableModel, is_active=False)
        m.delete(force=True)
        self.assertFalse(ActivatableModel.objects.exists())


class PreSyncdbTest(TestCase):
    """
    Tests that activatable models are validated properly upon pre_syncdb signal.
    """
    def test_get_activatable_models(self):
        activatable_models = get_activatable_models()
        self.assertEquals(set([ActivatableModel, ActivatableModelWRel]), set(activatable_models))

    def test_all_valid_models(self):
        """
        Tests emitting the pre_syncdb signal. All models should validate fine.
        """
        pre_syncdb.send(sender=self)

    @patch('activatable_model.models.get_activatable_models')
    def test_foreign_key_is_null(self, mock_get_activatable_models):
        """
        SET_NULL is a valid option for foreign keys in activatable models.
        """
        # Make this an object and not an actual django model. This prevents it from always
        # being included when syncing the db. This is true for all other test models in this file.
        class CascadableModel(BaseActivatableModel):
            class Meta:
                abstract = True

            ctype = models.ForeignKey(ContentType, null=True, on_delete=models.SET_NULL)

        mock_get_activatable_models.return_value = [CascadableModel]
        pre_syncdb.send(sender=self)
        self.assertEquals(mock_get_activatable_models.call_count, 1)

    @patch('activatable_model.models.get_activatable_models')
    def test_foreign_key_protect(self, mock_get_activatable_models):
        """
        PROTECT is a valid option for foreign keys in activatable models.
        """
        # Make this an object and not an actual django model. This prevents it from always
        # being included when syncing the db. This is true for all other test models in this file.
        class CascadableModel(BaseActivatableModel):
            class Meta:
                abstract = True

            ctype = models.ForeignKey(ContentType, null=True, on_delete=models.PROTECT)

        mock_get_activatable_models.return_value = [CascadableModel]
        pre_syncdb.send(sender=self)
        self.assertEquals(mock_get_activatable_models.call_count, 1)

    @patch('activatable_model.models.get_activatable_models')
    def test_foreign_key_cascade(self, mock_get_activatable_models):
        """
        The default cascade behavior is invalid for activatable models.
        """
        class CascadableModel(BaseActivatableModel):
            class Meta:
                abstract = True

            ctype = models.ForeignKey(ContentType)

        mock_get_activatable_models.return_value = [CascadableModel]
        with self.assertRaises(ValidationError):
            pre_syncdb.send(sender=self)

    @patch('activatable_model.models.get_activatable_models')
    def test_one_to_one_is_null(self, mock_get_activatable_models):
        """
        SET_NULL is a valid option for foreign keys in activatable models.
        """
        # Make this an object and not an actual django model. This prevents it from always
        # being included when syncing the db. This is true for all other test models in this file.
        class CascadableModel(BaseActivatableModel):
            class Meta:
                abstract = True

            ctype = models.OneToOneField(ContentType, null=True, on_delete=models.SET_NULL)

        mock_get_activatable_models.return_value = [CascadableModel]
        pre_syncdb.send(sender=self)
        self.assertEquals(mock_get_activatable_models.call_count, 1)

    @patch('activatable_model.models.get_activatable_models')
    def test_one_to_one_protect(self, mock_get_activatable_models):
        """
        PROTECT is a valid option for foreign keys in activatable models.
        """
        # Make this an object and not an actual django model. This prevents it from always
        # being included when syncing the db. This is true for all other test models in this file.
        class CascadableModel(BaseActivatableModel):
            class Meta:
                abstract = True

            ctype = models.OneToOneField(ContentType, null=True, on_delete=models.PROTECT)

        mock_get_activatable_models.return_value = [CascadableModel]
        pre_syncdb.send(sender=self)
        self.assertEquals(mock_get_activatable_models.call_count, 1)

    @patch('activatable_model.models.get_activatable_models')
    def test_one_to_one_cascade(self, mock_get_activatable_models):
        """
        The default cascade behavior is invalid for activatable models.
        """
        class CascadableModel(BaseActivatableModel):
            class Meta:
                abstract = True

            ctype = models.OneToOneField(ContentType)

        mock_get_activatable_models.return_value = [CascadableModel]
        with self.assertRaises(ValidationError):
            pre_syncdb.send(sender=self)
