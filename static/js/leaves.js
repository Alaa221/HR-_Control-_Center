(() => {
  const code = document.getElementById('leaveCode');
  const daysField = document.getElementById('leaveDaysField');
  const hoursField = document.getElementById('leaveHoursField');
  const startDate = document.querySelector('input[name="leave_date"]');
  const endDate = document.querySelector('input[name="end_date"]');
  if (!code || !daysField || !hoursField || !startDate || !endDate) return;

  const updateFields = () => {
    const permission = code.value === 'PERM';
    daysField.hidden = permission;
    hoursField.hidden = !permission;
    daysField.querySelector('input').value = permission ? '0' : '1';
    hoursField.querySelector('input').value = permission ? '1' : '0';
    endDate.readOnly = permission;
    if (permission) endDate.value = startDate.value;
  };
  code.addEventListener('change', updateFields);
  startDate.addEventListener('change', () => {
    if (code.value === 'PERM') endDate.value = startDate.value;
  });
  updateFields();
})();
