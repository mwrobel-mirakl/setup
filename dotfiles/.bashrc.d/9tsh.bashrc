if [ -x "$(command -v tsh)" ]; then
  eval "$(tsh --completion-script-bash | grep -v '^complete -F __bash_autocomplete -o default *$')"
fi
