# 07) کیفیت کد و CI

## هدف
قبل از merge شدن کد، کیفیت و سلامت پایه تضمین شود.

## اجزای فعلی

- `.editorconfig` → استاندارد indentation و newline
- `.pre-commit-config.yaml` → اجرای خودکار ruff/format قبل از commit
- `.github/workflows/ci.yml` → lint + test در GitHub Actions
- `backend/pytest.ini` + تست health endpoint

## اجرای local quality gate

```bash
make lint
make test
make check
```

## pre-commit

```bash
pip install pre-commit
pre-commit install
```

> در پروژه کاملاً Docker-based می‌توانید اجرای pre-commit را هم containerize کنید.

## چرا مهم است

- جلوگیری از ورود کد شکسته به شاخه اصلی
- یکسان شدن style بین اعضای تیم
- کاهش خطاهای تکراری در ریویو
