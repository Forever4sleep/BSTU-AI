import { Navigate } from "react-router-dom";

import { cabinetHomeHref } from "./cabinetPath";

/** По сохранённой роли отправляет на страницу профиля (студент / преподаватель / админ). */
export function CabinetRedirectPage() {
  return <Navigate to={cabinetHomeHref()} replace />;
}
