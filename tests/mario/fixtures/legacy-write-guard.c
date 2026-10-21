/* GPL-2.0: captured from our installed guard-fix build for regression tests. */
void store_erase(const uint8_t *flash_ptr, uint32_t size)
{
  if (flash_ptr == NULL) {
    return;
  }

  uintptr_t start = (uintptr_t)flash_ptr;
  uint32_t save_address = start - (uintptr_t)&__EXTFLASH_BASE__;
  assert((save_address & (4 * 1024 - 1)) == 0);

  // Validate the complete erased sector range, including any padding.
  assert(size <= UINT32_MAX - 4095u);
  size = (size + 4095u) & ~4095u;
  assert(size <= UINTPTR_MAX - start);
  uintptr_t end = start + size;
  assert(
#if NES_BATTERY_SAVE == 1
    ((start >= (uintptr_t)__BATTERYFLASH_START__) && (end <= (uintptr_t)__BATTERYFLASH_END__)) ||
#endif
    ((start >= (uintptr_t)&__OFFSAVEFLASH_START__) && (end <= (uintptr_t)&__OFFSAVEFLASH_END__)) ||
    ((start >= (uintptr_t)&__SAVEFLASH_START__) && (end <= (uintptr_t)&__SAVEFLASH_END__)) ||
    ((start >= (uintptr_t)&__configflash_start__) && (end <= (uintptr_t)&__configflash_end__)) ||
    ((start >= (uintptr_t)&__fbflash_start__) && (end <= (uintptr_t)&__fbflash_end__))
  );

  OSPI_DisableMemoryMappedMode();
  OSPI_EraseSync(save_address, size);
  OSPI_EnableMemoryMappedMode();
}
void store_save(const uint8_t *flash_ptr, const uint8_t *data, size_t size)
{
  // Temporary solution to make things work with flash with 256K erase pages
#ifdef DISABLE_STORE
  return;
#endif
  // Disable save data when save address is zero
  if (flash_ptr == 0) {
    return;
  }
  // Convert mem mapped pointer to flash address
  uint32_t save_address = flash_ptr - &__EXTFLASH_BASE__;

  // Only allow 4kB aligned pointers
  assert((save_address & (4*1024 - 1)) == 0);

  int diff = memcmp((void*)flash_ptr, data, size);
  if (diff == 0) {
    return;
  }

  store_erase(flash_ptr, size);

  OSPI_DisableMemoryMappedMode();
  OSPI_Program(save_address, data, size);
  OSPI_EnableMemoryMappedMode();
}
