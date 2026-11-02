" Minimal plugin used to test the vim preset.
if exists('g:loaded_demo')
  finish
endif
let g:loaded_demo = 1

command! Demo echo demo#greet()
