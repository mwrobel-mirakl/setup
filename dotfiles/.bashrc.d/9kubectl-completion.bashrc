if [ -x "$(command -v kubectl)" ]; then
  eval "$(kubectl completion bash)"
fi
