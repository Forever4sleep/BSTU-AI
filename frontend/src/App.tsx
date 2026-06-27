import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AdminPage } from "./AdminPage";
import { CabinetRedirectPage } from "./CabinetRedirectPage";
import { StudentLayout } from "./components/StudentLayout";
import { CoursePage } from "./CoursePage";
import { StudentChatPage } from "./StudentChatPage";
import { StudentCabinetPage } from "./StudentCabinetPage";
import { HomePage } from "./HomePage";
import { UnifiedLoginPage } from "./UnifiedLoginPage";
import { TeacherAuthProvider } from "./teacher/TeacherAuthContext";
import { TeacherCabinetPage } from "./teacher/TeacherCabinetPage";
import { TeacherChatPage } from "./teacher/TeacherChatPage";
import { TeacherCourseDetailPage } from "./teacher/TeacherCourseDetailPage";
import { TeacherDraftReviewPage } from "./teacher/TeacherDraftReviewPage";
import { TeacherProblemEditPage } from "./teacher/TeacherProblemEditPage";
import { TeacherCoursesPage } from "./teacher/TeacherCoursesPage";
import { TeacherDashboard } from "./teacher/TeacherDashboard";
import { TeacherShell } from "./teacher/TeacherShell";

/** Monaco грузится только при открытии задачи — не валит весь бандл/главную при ошибке CDN/wasm в Docker. */
const ProblemPage = lazy(() => import("./ProblemPage").then((m) => ({ default: m.ProblemPage })));

export default function App() {
  return (
    <BrowserRouter>
      <TeacherAuthProvider>
        <Routes>
          <Route path="/login" element={<UnifiedLoginPage />} />
          <Route path="/cabinet" element={<CabinetRedirectPage />} />
          <Route path="/admin/login" element={<Navigate to="/login" replace />} />
          <Route path="/student/login" element={<Navigate to="/login" replace />} />
          <Route path="/teacher/login" element={<Navigate to="/login" replace />} />
          <Route path="/admin" element={<AdminPage />} />

          <Route element={<StudentLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/student/cabinet" element={<StudentCabinetPage />} />
            <Route path="/student/chat" element={<StudentChatPage />} />
            <Route path="/c/:slug" element={<CoursePage />} />
            <Route
              path="/c/:slug/p/:problemId"
              element={
                <Suspense
                  fallback={
                    <div className="stu-main ds-card ds-animate-in" style={{ marginTop: "1.5rem" }}>
                      <p className="t-page__sub" style={{ margin: 0 }}>
                        Загружается редактор кода…
                      </p>
                    </div>
                  }
                >
                  <ProblemPage />
                </Suspense>
              }
            />
          </Route>

          <Route path="/teacher" element={<TeacherShell />}>
            <Route index element={<TeacherDashboard />} />
            <Route path="cabinet" element={<TeacherCabinetPage />} />
            <Route path="courses" element={<TeacherCoursesPage />} />
            <Route path="courses/:courseId" element={<TeacherCourseDetailPage />} />
            <Route path="courses/:courseId/problems/:problemId/edit" element={<TeacherProblemEditPage />} />
            <Route path="courses/:courseId/drafts/:draftId" element={<TeacherDraftReviewPage />} />
            <Route path="chat" element={<TeacherChatPage />} />
          </Route>

          <Route
            path="*"
            element={
              <div className="stu-main">
                <div className="ds-card">
                  <h1 className="t-page__title">404</h1>
                  <p className="ds-caption">Страница не найдена.</p>
                </div>
              </div>
            }
          />
        </Routes>
      </TeacherAuthProvider>
    </BrowserRouter>
  );
}
