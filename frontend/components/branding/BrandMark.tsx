import Image from "next/image";

export function BrandMark({className = "h-5 w-5"}: {className?: string}) {
  return (
    <Image
      src="/branding/job-hunter-mark.png"
      alt=""
      aria-hidden="true"
      width={1254}
      height={1254}
      className={`${className} object-contain`}
    />
  );
}
