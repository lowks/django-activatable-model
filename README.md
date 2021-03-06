[![Build Status](https://travis-ci.org/ambitioninc/django-activatable-model.png)](https://travis-ci.org/ambitioninc/django-activatable-model)
Django Activatable Model
==================
Provides functionality for Django models that have active and inactive states. Features of this app are:

1. An abstract BaseActivatableModel that provides an is_active flag
1. A model_activations_changed signal that fires when models' is_active flags are changed or bulk updated
1. Validation to ensure activatable models cannot be cascade deleted
1. Overriding of delete methods so that is_active is set to False instead of the model(s) being deleted (unless force=True)
1. Manager/QuerySet methods to activate and deactivate models

## Installation
```python
sudo pip install django-activatable-model
```

Add ``activatable_model`` to the list of ``INSTALLED_APPS``. Although this app does not define any concrete models, it does connect signals that Django needs to know about.

## Basic Usage
Assume you have a model called ``Account`` in your app, and it is an activatable model that has a ``name`` field and a ``ForeignKey`` to a ``Group`` model.

```python
from activatable_model import BaseActivatableModel

class Account(BaseActivatableModel):
    name = models.CharField(max_length=64)
    group = models.ForeignKey(Group)
```

By just inheriting ``BaseActivatableModel``, your model will have an ``is_active`` field that defaults to False. If you create an ``Account`` model, the ``model_activations_changed`` signal will be sent with an ``is_active`` keyword argument set to False and an ``instances`` keyword argument that is a list of the single created account. Similarly, if you updated the ``is_active`` flag at any time via the ``save`` method, the ``model_activations_changed`` signal will be emitted again. This allows the user to do things like this:

```python
from django.dispatch import receiver
from activatable_model import model_activations_changed

@receiver(model_activations_changed, sender=Account)
def do_something_on_deactivation(sender, instances, is_active, **kwargs):
    if not is_active:
        # Either an account was deactivated or an inactive account was created...
        for account in instances:
            # Do something with every deactivated account
```

## Activatable Model Deletion
Django activatable model is meant for models that should never be deleted but rather activated/deactivated instead. Given the assumption that activatable models should never be deleted, Django activatable model does some magic underneath to ensure your activatable models are properly updated when the user calls ``delete``. Instead of deleting the object(s) directly, the ``is_active`` flag is set to False and ``model_activations_changed`` is fired.

```python
account = Account.objects.create(is_active=True)
account.delete()  # Or Account.objects.all().delete()

# The account still exists
print Account.objects.count()
1

# But it is deactivated
print Account.objects.get().is_active
False
```

The user can override this behavior by passing ``force=True`` to the model or queryset's ``delete`` method.

Along with overriding deletion, Django activatable model also overrides cascade deletion. No model that inherits ``BaseActivatableModel`` can be cascade deleted by another model. This is accomplished by connecting to Django's ``pre_syncdb`` signal and verifying that all ``ForeignKey`` and ``OneToOneField`` fields of activatable models have their ``on_delete`` arguments set to something other than the default of ``models.CASCADE``.

In fact, our ``Account`` model will not pass validation. In order to make it validate properly on syncdb, it must do the following:

```python
from django.db import models

class Account(BaseActivatableModel):
    name = models.CharField(max_length=64)
    group = models.ForeignKey(Group, on_delete=models.PROTECT)
```

This will ensure a ``ProtectedError`` is thrown everytime a Group is deleted. For other options on foreign key deletion behavior, go to https://docs.djangoproject.com/en/1.6/ref/models/fields/#django.db.models.ForeignKey.on_delete.

## Manager and QuerySet methods
Django activatable models automatically use an ``ActivatableManager`` manager that uses an ``ActivatableQuerySet`` queryset. This provides the following functionality:

1. Two methods - ``activate()`` and ``deactivate()`` that can be applied to a queryset
1. Overriding the ``update()`` method so that it emits ``model_activations_changed`` when the ``is_active`` flag is updated
1. Overriding the ``delete()`` method so that it calls ``deactivate()`` unless ``force=True``

## License
MIT License (see the LICENSE file in this repo)