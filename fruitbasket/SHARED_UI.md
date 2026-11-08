# Shared visual foundation

All three base templates load local Bootstrap 5.3.3 followed by `store/css/site.css`. There is no CDN dependency, JavaScript navigation, or build step. Header and navigation partials remain in their original locations, and the existing `content` blocks remain available to child templates. Authentication templates and individual content templates were not edited.

## Static discovery

`django.contrib.staticfiles` and `store` are already in `INSTALLED_APPS`. Django's app static finder searches `store/static/`, so `{% static 'store/css/site.css' %}` resolves to `/static/store/css/site.css`. The second `store` directory namespaces the asset and prevents filename collisions. Static discovery is project-wide: adminpanel and public templates can use that same path even though the file belongs to store. Bootstrap lives alongside it at `store/vendor/bootstrap/bootstrap.min.css`; the upstream MIT license is included.

With DEBUG enabled, `python manage.py runserver` serves discovered assets. Verify discovery using `python manage.py findstatic store/css/site.css store/vendor/bootstrap/bootstrap.min.css`. Production requires collectstatic and a configured static-file server; this change does not configure production hosting.

## Conventions

Use `btn btn-primary` for the main action, `btn btn-secondary` for secondary actions and `btn btn-danger` for destructive actions. Existing content templates receive Bootstrap defaults; their individual layouts remain a separate task. Navigation uses named URLs and `request.resolver_match.url_name`, including detail URLs sharing a route name. Existing customer session visibility is preserved.

All bases include `store/shared/messages.html`. Django message levels select success, warning, error or information text and colours. The message itself supplies the explanation; state is never conveyed by colour alone. The common stylesheet adds keyboard focus and a skip link.

## Verification

Source checks verify named navigation routes, included templates, content blocks, local CSS ordering, and removal of floats in the shared shell. Django execution and browser verification were not available in the editing environment because Django could not be installed. On your machine, run `python manage.py check`, `python manage.py findstatic store/css/site.css store/vendor/bootstrap/bootstrap.min.css`, and `python manage.py test`. Check public, customer (signed in/out), and staff pages at 375px and 1440px; tab through navigation, follow the skip link, and trigger success/warning/error messages.

## Defence pitch

The old percentage-based floats reserved a separate column for navigation even on small screens. Flexbox now allows navigation links to wrap, while all three areas share locally served CSS and accessible message presentation.
