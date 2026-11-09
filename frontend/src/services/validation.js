const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Same rules as the backend (backend/app.py /contact); the server re-checks.
export function validateContact(form) {
  const errors = {};
  if (form.name.trim().length > 100) errors.name = "Name must be 100 characters or fewer.";
  if (!EMAIL_RE.test(form.email.trim())) errors.email = "Please enter a valid email address.";
  if (!form.subject.trim()) errors.subject = "Please enter a subject.";
  else if (form.subject.trim().length > 150) errors.subject = "Subject must be 150 characters or fewer.";
  const length = form.message.trim().length;
  if (length < 10) errors.message = "Please write at least 10 characters.";
  else if (length > 5000) errors.message = "Message must be 5000 characters or fewer.";
  return errors;
}
