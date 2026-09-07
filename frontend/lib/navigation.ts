import {
  BarChart3,
  BriefcaseBusiness,
  FileText,
  FileSearch,
  FolderOpen,
  LayoutDashboard,
  Library,
  Settings,
  Sparkles,
  UserRound
} from "lucide-react";

export const navItems = [
  {href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard},
  {href: "/jobs", labelKey: "nav.jobs", icon: BriefcaseBusiness},
  {href: "/applications", labelKey: "nav.applications", icon: FolderOpen},
  {href: "/resumes", labelKey: "nav.resumes", icon: FileText},
  {href: "/resume-match", labelKey: "nav.resumeMatch", icon: FileSearch},
  {href: "/profile", labelKey: "nav.profile", icon: UserRound},
  {href: "/experiences", labelKey: "nav.experiences", icon: Library},
  {href: "/interviews", labelKey: "nav.interviews", icon: Sparkles},
  {href: "/analytics", labelKey: "nav.analytics", icon: BarChart3},
  {href: "/settings", labelKey: "nav.settings", icon: Settings}
];
