import {
  BriefcaseBusiness,
  FileText,
  FileSearch,
  FolderOpen,
  LayoutDashboard,
  Library,
  Settings,
  Sparkles
} from "lucide-react";

export const navItems = [
  {href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard},
  {href: "/jobs", labelKey: "nav.jobs", icon: BriefcaseBusiness},
  {href: "/applications", labelKey: "nav.applications", icon: FolderOpen},
  {href: "/resumes", labelKey: "nav.resumes", icon: FileText},
  {href: "/resume-match", labelKey: "nav.resumeMatch", icon: FileSearch},
  {href: "/experiences", labelKey: "nav.experiences", icon: Library},
  {href: "/interviews", labelKey: "nav.interviews", icon: Sparkles},
  {href: "/settings", labelKey: "nav.settings", icon: Settings}
];
