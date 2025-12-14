export PYFILES=$(git ls-files "*.py")
flake8 --count --verbose $PYFILES
pylint $PYFILES
