#!/bin/sh
set -eu

CHECK_ORDER="suppressions ruff-format ruff-check ty pytest admin-build admin-test"

dry_run=0
only_checks=""
skip_checks=""

show_usage() {
    cat <<'USAGE'
Usage: ci.sh [options]

Runs the same local checks enforced by GitHub CI (.github/workflows/tests.yml).
Requires uv on PATH when running ruff, ty, or pytest checks.

Checks (in order):
  suppressions   Ban # type: ignore / # ty: ignore suppressions
  ruff-format    uv run ruff format --check
  ruff-check     uv run ruff check
  ty             uv run ty check
  pytest         uv run pytest -v --tb=short
  admin-build    npm ci && npm run build && git diff --exit-code api/admin_static/
  admin-test     npm ci && npm test

Options:
  --only ID                Run only the given check (repeatable)
  --skip ID                Skip the given check (repeatable)
  --dry-run                Print commands without running them.
  --help                   Show this help text.
USAGE
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

step() {
    printf '\n==> %s\n' "$1"
}

quote_arg() {
    case "$1" in
        *[!A-Za-z0-9_./:@%+=,-]*|"")
            escaped=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')
            printf '"%s"' "$escaped"
            ;;
        *)
            printf '%s' "$1"
            ;;
    esac
}

print_command() {
    printf '+'
    for arg in "$@"; do
        printf ' '
        quote_arg "$arg"
    done
    printf '\n'
}

run() {
    print_command "$@"
    if [ "$dry_run" -eq 0 ]; then
        "$@"
    fi
}

valid_check_id() {
    case "$1" in
        suppressions | ruff-format | ruff-check | ty | pytest | admin-build | admin-test) return 0 ;;
        *) return 1 ;;
    esac
}

validate_check_id() {
    if ! valid_check_id "$1"; then
        fail "unknown check id: $1 (expected one of: $CHECK_ORDER)"
    fi
}

contains_check_id() {
    list=$1
    id=$2
    case " $list " in
        *" $id "*) return 0 ;;
        *) return 1 ;;
    esac
}

should_run_check() {
    check_id=$1

    if [ -n "$only_checks" ] && ! contains_check_id "$only_checks" "$check_id"; then
        return 1
    fi

    if contains_check_id "$skip_checks" "$check_id"; then
        return 1
    fi

    return 0
}

assert_uv_available() {
    if ! command -v uv >/dev/null 2>&1; then
        fail "uv is required but was not found on PATH. Install uv first (see README or scripts/install.sh)."
    fi
}

selected_checks_need_uv() {
    if [ "$dry_run" -ne 0 ]; then
        return 1
    fi

    for check_id in $CHECK_ORDER; do
        if should_run_check "$check_id" ] && [ "$check_id" != "suppressions" ] && [ "$check_id" != "admin-build" ] && [ "$check_id" != "admin-test" ]; then
            return 0
        fi
    done

    return 1
}

run_suppressions() {
    step "Ban type ignore suppressions"
    print_command grep -rE '# type: ignore|# ty: ignore' --include='*.py' . \
        --exclude-dir=.venv --exclude-dir=.git
    if [ "$dry_run" -eq 0 ]; then
        if grep -rE '# type: ignore|# ty: ignore' --include='*.py' . \
            --exclude-dir=.venv --exclude-dir=.git; then
            fail "type: ignore / ty: ignore comments are not allowed. Fix the underlying type errors instead."
        fi
    fi
}

run_ruff_format() {
    step "ruff format --check"
    run uv run ruff format --check
}

run_ruff_check() {
    step "ruff check"
    run uv run ruff check
}

run_ty() {
    step "ty check"
    run uv run ty check
}

run_pytest() {
    step "pytest"
    run uv run pytest -v --tb=short
}

run_admin_build() {
    step "admin-build (npm run build + freshness)"
    if ! command -v npm >/dev/null 2>&1; then
        printf 'warning: npm not found on PATH — skipping admin-build locally.\n' >&2
        printf '         The admin-build CI job is the hard gate; this local check is optional.\n' >&2
        return 0
    fi
    print_command npm ci
    if [ "$dry_run" -eq 0 ]; then
        npm ci
    fi
    print_command npm run build
    if [ "$dry_run" -eq 0 ]; then
        npm run build
    fi
    print_command git diff --exit-code api/admin_static/
    if [ "$dry_run" -eq 0 ]; then
        if ! git diff --exit-code api/admin_static/ >/dev/null 2>&1; then
            fail "api/admin_static/ artefacts are stale. Run 'npm run build' and commit the regenerated files."
        fi
    fi
}

run_admin_test() {
    step "admin-test (npm test)"
    if ! command -v npm >/dev/null 2>&1; then
        printf 'warning: npm not found on PATH — skipping admin-test locally.\n' >&2
        printf '         The admin-test CI job is the hard gate; this local check is optional.\n' >&2
        return 0
    fi
    print_command npm ci
    if [ "$dry_run" -eq 0 ]; then
        npm ci
    fi
    print_command npm test
    if [ "$dry_run" -eq 0 ]; then
        npm test
    fi
}

run_check() {
    case "$1" in
        suppressions) run_suppressions ;;
        ruff-format) run_ruff_format ;;
        ruff-check) run_ruff_check ;;
        ty) run_ty ;;
        pytest) run_pytest ;;
        admin-build) run_admin_build ;;
        admin-test) run_admin_test ;;
        *) fail "unknown check id: $1" ;;
    esac
}

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --only)
                shift
                [ "$#" -gt 0 ] || fail "--only requires a check id."
                validate_check_id "$1"
                only_checks="${only_checks} $1"
                ;;
            --skip)
                shift
                [ "$#" -gt 0 ] || fail "--skip requires a check id."
                validate_check_id "$1"
                skip_checks="${skip_checks} $1"
                ;;
            --dry-run)
                dry_run=1
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                show_usage >&2
                fail "unknown option: $1"
                ;;
        esac
        shift
    done
}

parse_args "$@"
if selected_checks_need_uv; then
    assert_uv_available
fi

for check_id in $CHECK_ORDER; do
    if should_run_check "$check_id"; then
        run_check "$check_id"
    fi
done

printf '\nAll selected CI checks passed.\n'
